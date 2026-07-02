import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import {
  X,
  Play,
  RefreshCw,
  AlertTriangle,
  Network,
  Check,
  Upload,
  RotateCcw,
  Loader2,
} from 'lucide-react';
import OntologyMetadataForm from './OntologyMetadataForm';
import { API_METHODS } from '../services/apiClient';
import { apiClient } from '../services/apiClient';
import { useOntologies } from '../contexts/OntologyContext';
import { API, buildUrl, replaceParams } from '../config';
import {
  backendToFrontendStage,
  buildWorkflowStages,
  getStageLabel,
  getWorkflowDisplayName,
  inferFileTypeFromExtension,
  isImportWorkflow,
  mergeWorkflowRuntimeOptions,
  recommendWorkflowForFile,
  resolveWorkflow,
  supportedFormats,
  workflowCatalog,
} from '../workflows/workflowEngine';

// Design tokens (matching OntologyMapper & GraphHEB)
const C = {
  primary:      '#004B87',
  primaryDark:  '#003366',
  primaryLight: '#E8F1FC',
  green:        '#28A745',
  orange:       '#FFC107',
  red:          '#D32F2F',
  textPrimary:  '#1A2B3C',
  textSec:      '#6C757D',
  textMuted:    '#ADB5BD',
  border:       '#E9ECEF',
  borderDark:   '#CED4DA',
  bg:           '#F8F9FA',
  surface:      '#FFFFFF',
  darkBg:       '#2C3E50',
};

const IMPORT_JOBS_STORAGE_KEY = 'depo.import.jobs.v2';
const IMPORT_ONTOLOGIES_CACHE_KEY = 'depo.import.ontologies.v1';
const PRIMARY_WORKFLOW_IDS = new Set(['instance.import', 'ontology.create', 'architecture.archimate', 'document.unstructured', 'instance.link']);
const RESUMABLE_JOB_MAX_AGE_MS = 6 * 60 * 60 * 1000;
const ONTOLOGY_SOURCE_TYPES = new Set(['ontology', 'xsd', 'xmi', 'express']);
const ONTOLOGY_METADATA_EXTENSIONS = new Set(['.xsd', '.xmi', '.mdxml', '.owl', '.rdf', '.ttl', '.exp']);


function serializeFileForPersistence(file) {
  if (!file) return null;
  const { fileObj, ...rest } = file;
  return {
    ...rest,
    fileObj: null,
    persisted: true,
  };
}

function getStatusTimestamp(status = {}, file = null) {
  return (
    status.lastUpdatedAt ||
    status.completedAtIso ||
    file?.updatedAt ||
    file?.createdAt ||
    null
  );
}

function isTerminalPipelineStatus(status = {}) {
  return Boolean(
    status.error ||
    status.status === 'failed' ||
    status.committed ||
    status.status === 'completed' ||
    status.commitPhase === 'complete' ||
    status.progress === 100
  );
}

function isResumablePersistedJob(file, status) {
  if (!file?.taskId || !status) return false;
  if (isTerminalPipelineStatus(status)) return false;
  const stamp = getStatusTimestamp(status, file);
  if (!stamp) return false;
  const parsed = Date.parse(stamp);
  if (Number.isNaN(parsed)) return false;
  return (Date.now() - parsed) <= RESUMABLE_JOB_MAX_AGE_MS;
}

function getFileExtensionFromName(fileName = '') {
  const parts = String(fileName).split('.');
  return parts.length > 1 ? `.${parts.pop().toLowerCase()}` : '';
}

function isOntologySourceFile(fileName = '') {
  return ONTOLOGY_SOURCE_TYPES.has(inferFileTypeFromExtension(fileName));
}

function requiresOntologyMetadataCapture(fileName = '') {
  return ONTOLOGY_METADATA_EXTENSIONS.has(getFileExtensionFromName(fileName));
}

function getWorkflowNote({
  canRunSelectedWorkflow,
  fallbackWorkflow,
  mappingFileTypeContext,
  selectedWorkflow,
  selectedImportArtifactEntry,
}) {
  if (!canRunSelectedWorkflow) {
    return `${fallbackWorkflow.title} is not connected yet.`;
  }
  if (selectedWorkflow === 'instance.link') {
    if (!selectedImportArtifactEntry) {
      return 'Select one completed import artifact first, then choose the ontology you want to align against.';
    }
    return 'Review one imported instance artifact against one ontology, then preview or apply semantic mappings.';
  }
  if (selectedWorkflow === 'ontology.create') {
    return 'Use this workflow only for ontology or schema registration. XSD, OWL, RDF, TTL, XMI, MDXML, and EXPRESS files belong here; instance files belong in Import instance graph.';
  }
  if (selectedWorkflow === 'architecture.archimate') {
    return 'Upload ArchiMate Model Exchange XML to create a process-reference architecture graph with typed relationships.';
  }
  if (selectedWorkflow === 'ontology.merge') {
    return 'Select a source ontology and a different target ontology, then review the merge plan.';
  }
  if (
    selectedWorkflow === 'ontology.validate'
    || selectedWorkflow === 'dictionary.generate'
    || selectedWorkflow === 'taxonomy.generate'
    || selectedWorkflow === 'graph.chunk'
  ) {
    return 'Select an ontology to generate the artifact.';
  }
  if (mappingFileTypeContext === 'express') {
    return 'EXPRESS creates ontology structure.';
  }
  if (mappingFileTypeContext === 'step') {
    return 'STEP imports instance data with AP242 context.';
  }
  if (selectedWorkflow === 'instance.import' && (mappingFileTypeContext === 'csv' || mappingFileTypeContext === 'excel')) {
    return 'CSV and Excel import as source data first.';
  }
  if (
    selectedWorkflow === 'instance.import'
    && ['json', 'xml', 'plmxml', '3dxml'].includes(mappingFileTypeContext)
  ) {
    return 'JSON, XML, PLMXML, and 3DXML import as source data first.';
  }
  if (selectedWorkflow === 'instance.import' && ['ontology', 'xsd', 'xmi', 'express'].includes(mappingFileTypeContext)) {
    return 'Use Create ontology for OWL, RDF, TTL, XSD, XMI, MDXML, or EXPRESS files.';
  }
  if (selectedWorkflow === 'instance.import' && !mappingFileTypeContext) {
    return 'Select files to continue.';
  }
  return 'Ready.';
}

export default function DataImportPipeline() {
  const [files, setFiles] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState({});
  const [error, setError] = useState(null);
  const [startedFiles, setStartedFiles] = useState(new Set());
  const [selectedStage, setSelectedStage] = useState('upload');
  const [previewData, setPreviewData] = useState(null);
  const [confirmingImport, setConfirmingImport] = useState(null);
  const [preCheck, setPreCheck] = useState(null); // { loading, ready, checks, reason }
  const fileInputRef = useRef(null);
  const [selectedWorkflow, setSelectedWorkflow] = useState('instance.import');
  const [showAdvancedWorkflows, setShowAdvancedWorkflows] = useState(false);
  const [workflowOptions, setWorkflowOptions] = useState(workflowCatalog);
  const [workflowOntologyId, setWorkflowOntologyId] = useState('');
  const [workflowTargetOntologyId, setWorkflowTargetOntologyId] = useState('');
  const [workflowSourceFileId, setWorkflowSourceFileId] = useState('');
  const [workflowRun, setWorkflowRun] = useState(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowApplyLinks, setWorkflowApplyLinks] = useState(false);

  function normalizeOntologyOptions(ontologyList = []) {
    const allOntologies = ontologyList.map(ont => ({
      id: ont.ontology_id || ont.id || ont.value || ont.prefix,
      value: ont.value || ont.ontology_id || ont.id || ont.prefix || ont.name,
      name: ont.label || ont.ontology_name || ont.name,
      file: ont.raw?.original_filename || ont.raw?.stored_filename || ont.name,
      prefix: ont.prefix || ont.ontology_prefix || '',
      uploaded_at: ont.raw?.uploaded_at || ont.raw?.uploadedAt || '',
      source: ont.source,
      usage_count: ont.raw?.usageCount || ont.raw?.usage_count || 0,
      last_used: ont.raw?.lastUsed || ont.raw?.last_used || '',
    }));
    const byOptionKey = new Map();
    allOntologies.forEach((o) => {
      const optionKey = `${o.value || o.id || 'unknown'}:${o.prefix || 'no-prefix'}:${o.file || 'no-file'}`;
      if (!byOptionKey.has(optionKey) || o.uploaded_at > (byOptionKey.get(optionKey).uploaded_at || '')) {
        byOptionKey.set(optionKey, {
          ...o,
          optionKey,
          optionValue: o.value || o.id || `${o.prefix}:${o.file}`,
        });
      }
    });
    return Array.from(byOptionKey.values());
  }

  const [availableOntologies, setAvailableOntologies] = useState(() => {
    try {
      const cached = JSON.parse(window.localStorage.getItem(IMPORT_ONTOLOGIES_CACHE_KEY) || '[]');
      return normalizeOntologyOptions(cached);
    } catch (_err) {
      return [];
    }
  });
  const [mappingFileTypeContext, setMappingFileTypeContext] = useState('');
  
  // Ontology metadata form for XSD/XMI files
  const [showMetadataForm, setShowMetadataForm] = useState(false);
  const [pendingFileForMetadata, setPendingFileForMetadata] = useState(null);
  const [pendingMetadataFileId, setPendingMetadataFileId] = useState('');
  const [pendingMetadataQueue, setPendingMetadataQueue] = useState([]);
  const [isMetadataLoading, setIsMetadataLoading] = useState(false);
  const [metadataFormPrefill, setMetadataFormPrefill] = useState(null);
  const didRestoreJobsRef = useRef(false);
  const resumedPersistedJobsRef = useRef(false);
  const activePollersRef = useRef(new Set());
  const [ontologyCatalogState, setOntologyCatalogState] = useState({
    loading: availableOntologies.length === 0,
    stale: false,
    message: '',
    source: availableOntologies.length > 0 ? 'cache' : 'none',
    lastLoadedAt: null,
  });

  // Get ontologies from centralized context (shared across all components)
  const { ontologies: contextOntologies } = useOntologies();

  const loadOntologyOptions = useCallback(async ({ forceLive = false } = {}) => {
    const cachedRaw = window.localStorage.getItem(IMPORT_ONTOLOGIES_CACHE_KEY);
    const cachedOntologies = (() => {
      try {
        return normalizeOntologyOptions(cachedRaw ? JSON.parse(cachedRaw) : []);
      } catch (_err) {
        return [];
      }
    })();

    setOntologyCatalogState((prev) => ({ ...prev, loading: true, message: forceLive ? 'Refreshing ontology catalog...' : prev.message }));

    try {
      let sourceOntologies = !forceLive ? contextOntologies : [];
      if (!sourceOntologies?.length) {
        let lastErr = null;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            const response = await API_METHODS.ontology.listRegistered();
            sourceOntologies = response?.data?.ontologies || [];
            lastErr = null;
            break;
          } catch (err) {
            lastErr = err;
            await new Promise((resolve) => setTimeout(resolve, 700 * (attempt + 1)));
          }
        }
        if (lastErr) throw lastErr;
      }
      const normalized = normalizeOntologyOptions(sourceOntologies);
      if (normalized.length > 0) {
        setAvailableOntologies(normalized);
        window.localStorage.setItem(IMPORT_ONTOLOGIES_CACHE_KEY, JSON.stringify(normalized));
        setOntologyCatalogState({
          loading: false,
          stale: false,
          message: '',
          source: 'live',
          lastLoadedAt: new Date().toISOString(),
        });
      } else if (cachedOntologies.length > 0) {
        setAvailableOntologies(cachedOntologies);
        setOntologyCatalogState({
          loading: false,
          stale: true,
          message: 'Using cached ontology catalog while the latest registry data catches up.',
          source: 'cache',
          lastLoadedAt: new Date().toISOString(),
        });
      } else {
        setOntologyCatalogState({
          loading: false,
          stale: false,
          message: 'Ontology catalog is still loading.',
          source: 'none',
          lastLoadedAt: null,
        });
      }
    } catch (err) {
      console.error('Failed to process ontologies:', err);
      if (cachedOntologies.length > 0) {
        setAvailableOntologies(cachedOntologies);
        setOntologyCatalogState({
          loading: false,
          stale: true,
          message: 'Using cached ontology catalog because the live registry is temporarily unavailable.',
          source: 'cache',
          lastLoadedAt: new Date().toISOString(),
        });
        return;
      }
      setOntologyCatalogState({
        loading: false,
        stale: false,
        message: 'Ontology catalog is temporarily unavailable. Retry in a moment.',
        source: 'none',
        lastLoadedAt: null,
      });
    }
  }, [contextOntologies]);

  // Transform context ontologies into DataImportPipeline format
  useEffect(() => {
    loadOntologyOptions();
  }, [loadOntologyOptions]);

  

  useEffect(() => {
    const loadWorkflowOptions = async () => {
      try {
        const response = await API_METHODS.workflow.getOptions();
        const runtimeOptions = response?.data?.workflows || [];
        setWorkflowOptions(mergeWorkflowRuntimeOptions(workflowCatalog, runtimeOptions));
      } catch (_err) {
        setWorkflowOptions(workflowCatalog);
      }
    };

    loadWorkflowOptions();
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(IMPORT_JOBS_STORAGE_KEY);
      if (!raw) {
        didRestoreJobsRef.current = true;
        return;
      }
      const saved = JSON.parse(raw);
      if (Array.isArray(saved.files) && saved.files.length) {
        setFiles(saved.files);
      }
      if (saved.pipelineStatus && typeof saved.pipelineStatus === 'object') {
        setPipelineStatus(saved.pipelineStatus);
      }
      if (Array.isArray(saved.startedFiles) && saved.startedFiles.length) {
        setStartedFiles(new Set(saved.startedFiles));
      }
    } catch (restoreErr) {
      console.warn('[import-jobs] restore failed:', restoreErr);
    } finally {
      didRestoreJobsRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!didRestoreJobsRef.current) return;
    try {
      const payload = {
        savedAt: new Date().toISOString(),
        files: files.map(serializeFileForPersistence).filter(Boolean),
        pipelineStatus,
        startedFiles: Array.from(startedFiles),
      };
      window.localStorage.setItem(IMPORT_JOBS_STORAGE_KEY, JSON.stringify(payload));
    } catch (persistErr) {
      console.warn('[import-jobs] persist failed:', persistErr);
    }
  }, [files, pipelineStatus, startedFiles]);

  useEffect(() => {
    const pending = files.find(f => !startedFiles.has(f.fileId));
    const contextFile = pending || pendingFileForMetadata || files[0];
    const fileTypeContext = contextFile ? inferFileTypeFromExtension(contextFile.name) : '';
    setMappingFileTypeContext(fileTypeContext);
  }, [files, startedFiles, pendingFileForMetadata]);

  useEffect(() => {
    if (selectedWorkflow !== 'ontology.merge' && workflowTargetOntologyId) {
      setWorkflowTargetOntologyId('');
      return;
    }
    if (selectedWorkflow === 'ontology.merge' && workflowTargetOntologyId && workflowTargetOntologyId === workflowOntologyId) {
      setWorkflowTargetOntologyId('');
    }
  }, [selectedWorkflow, workflowOntologyId, workflowTargetOntologyId]);

  useEffect(() => {
    if (selectedWorkflow !== 'instance.link' && workflowApplyLinks) {
      setWorkflowApplyLinks(false);
    }
  }, [selectedWorkflow, workflowApplyLinks]);

  useEffect(() => {
    if (selectedWorkflow !== 'instance.link' && workflowSourceFileId) {
      setWorkflowSourceFileId('');
    }
  }, [selectedWorkflow, workflowSourceFileId]);

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files);
    }
    e.target.value = '';
  };

  const queueOntologyRegistration = (selectedOntologyFiles) => {
    const queuedFiles = selectedOntologyFiles.map(file => ({
      fileId: file.name + '_' + Math.random().toString(36).substr(2, 9),
      name: file.name,
      size: file.size,
      fileObj: file,
      workflowId: 'ontology.create',
      createdAt: new Date().toLocaleTimeString(),
      pendingMetadata: true,
      description: '',
      generationType: '',
      schemaType: 'schema',
      prefix: '',
      ontologyName: '',
    }));

    setFiles(prev => [...prev, ...queuedFiles]);
    setPipelineStatus(prev => {
      const next = { ...prev };
      queuedFiles.forEach((file) => {
        next[file.fileId] = {
          stage: 'upload',
          backendStage: 'upload',
          progress: 0,
          status: 'pending',
          message: requiresOntologyMetadataCapture(file.name)
            ? 'Add ontology details to continue'
            : 'Ready for ontology registration',
          error: false,
        };
      });
      return next;
    });
    setPendingMetadataQueue(prev => [...prev, ...queuedFiles.map(file => file.fileId)]);
    setError(null);
  };

  const queueInstanceImports = (selectedInstanceFiles, workflowId = 'instance.import') => {
    const filesWithIds = selectedInstanceFiles.map(file => ({
      fileId: file.name + '_' + Math.random().toString(36).substr(2, 9),
      name: file.name,
      size: file.size,
      fileObj: file,
      workflowId,
      createdAt: new Date().toLocaleTimeString()
    }));

    setFiles(prev => [...prev, ...filesWithIds]);
    setError(null);
  };

  const handleFiles = (fileList) => {
    const newFiles = Array.from(fileList).filter(file => {
      const ext = getFileExtensionFromName(file.name);
      return supportedFormats.some(f => f.ext === ext);
    });

    if (newFiles.length === 0) {
      setError('No supported files. Accepted: ' + supportedFormats.map(f => f.ext).join(', '));
      return;
    }

    const MAX_SIZE = 500 * 1024 * 1024;
    const oversized = newFiles.filter(f => f.size > MAX_SIZE);
    if (oversized.length > 0) {
      setError(`File too large (max 500 MB): ${oversized.map(f => f.name).join(', ')}`);
      return;
    }

    const ontologyFiles = newFiles.filter((file) => isOntologySourceFile(file.name));
    const documentFiles = newFiles.filter((file) => inferFileTypeFromExtension(file.name) === 'document');
    const isArchimateWorkflowFile = (file) => (
      inferFileTypeFromExtension(file.name) === 'archimate'
      || (selectedWorkflow === 'architecture.archimate' && getFileExtensionFromName(file.name) === '.xml')
    );
    const archimateFiles = newFiles.filter(isArchimateWorkflowFile);
    const instanceFiles = newFiles.filter((file) => (
      !isOntologySourceFile(file.name)
      && !isArchimateWorkflowFile(file)
      && inferFileTypeFromExtension(file.name) !== 'document'
    ));

    const routeToOntologyWorkflow = selectedWorkflow === 'instance.import' && ontologyFiles.length > 0 && instanceFiles.length === 0 && archimateFiles.length === 0 && documentFiles.length === 0;
    const routeToArchitectureWorkflow = selectedWorkflow === 'instance.import' && archimateFiles.length > 0 && instanceFiles.length === 0 && ontologyFiles.length === 0 && documentFiles.length === 0;
    const routeToDocumentWorkflow = selectedWorkflow === 'instance.import' && documentFiles.length > 0 && instanceFiles.length === 0 && ontologyFiles.length === 0 && archimateFiles.length === 0;
    const routeToInstanceWorkflow = ['ontology.create', 'architecture.archimate', 'document.unstructured'].includes(selectedWorkflow) && instanceFiles.length > 0 && ontologyFiles.length === 0 && archimateFiles.length === 0 && documentFiles.length === 0;
    const effectiveWorkflow = routeToOntologyWorkflow
      ? 'ontology.create'
      : routeToArchitectureWorkflow
        ? 'architecture.archimate'
        : routeToDocumentWorkflow
          ? 'document.unstructured'
          : routeToInstanceWorkflow
            ? 'instance.import'
            : selectedWorkflow;

    if (effectiveWorkflow !== selectedWorkflow) {
      setSelectedWorkflow(effectiveWorkflow);
    }

    if (effectiveWorkflow === 'ontology.create') {
      const wrongFiles = [...instanceFiles, ...archimateFiles, ...documentFiles];
      if (wrongFiles.length > 0) {
        setError(`Create ontology only accepts ontology or schema sources. Move these files to the appropriate import workflow: ${wrongFiles.map((file) => file.name).join(', ')}`);
        return;
      }

      if (ontologyFiles.length === 0) {
        setError('Select an ontology or schema file to continue.');
        return;
      }

      queueOntologyRegistration(ontologyFiles);
      return;
    }

    if (effectiveWorkflow === 'architecture.archimate') {
      if (ontologyFiles.length > 0 || instanceFiles.length > 0 || documentFiles.length > 0) {
        setError(`Import ArchiMate process model only accepts ArchiMate Model Exchange files. Remove: ${[...ontologyFiles, ...instanceFiles, ...documentFiles].map((file) => file.name).join(', ')}`);
        return;
      }
      if (archimateFiles.length === 0) {
        setError('Select an ArchiMate Model Exchange file to continue.');
        return;
      }
      queueInstanceImports(archimateFiles, 'architecture.archimate');
      return;
    }

    if (effectiveWorkflow === 'document.unstructured') {
      if (ontologyFiles.length > 0 || instanceFiles.length > 0 || archimateFiles.length > 0) {
        setError(`Unstructured document pipeline only accepts PDF, Word, or PowerPoint files. Remove: ${[...ontologyFiles, ...instanceFiles, ...archimateFiles].map((file) => file.name).join(', ')}`);
        return;
      }
      if (documentFiles.length === 0) {
        setError('Select a PDF, Word, or PowerPoint file to continue.');
        return;
      }
      queueInstanceImports(documentFiles, 'document.unstructured');
      return;
    }

    if (effectiveWorkflow === 'instance.import' && (ontologyFiles.length > 0 || archimateFiles.length > 0 || documentFiles.length > 0)) {
      const wrongFiles = [...ontologyFiles, ...archimateFiles, ...documentFiles];
      setError(`Import instance graph only accepts structured source data files. Move these files to the appropriate workflow: ${wrongFiles.map((file) => file.name).join(', ')}`);
      return;
    }

    queueInstanceImports(instanceFiles, 'instance.import');
  };

  // Handle metadata form submission for ontology files
  const handleMetadataSubmit = async (metadata) => {
    if (!pendingFileForMetadata) return;

    setIsMetadataLoading(true);

    try {
      const fileId = pendingMetadataFileId || pendingFileForMetadata.name + '_' + Math.random().toString(36).substr(2, 9);

      setFiles(prev => prev.map(f => (
        f.fileId === fileId
          ? {
              ...f,
              ontologyName: metadata.ontologyName,
              prefix: metadata.prefix,
              generationType: metadata.generationType,
              description: metadata.description || '',
              schemaType: metadata.schemaType || 'schema',
              fileType: metadata.fileType,
              pendingMetadata: false,
            }
          : f
      )));
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          stage: 'upload',
          backendStage: 'upload',
          progress: 0,
          status: 'pending',
          message: `Metadata saved for '${metadata.ontologyName}'. Click Start to register ontology.`,
          error: false,
        }
      }));
      setPendingMetadataQueue(prev => prev.filter(id => id !== fileId));
      setMetadataFormPrefill(null);
      setShowMetadataForm(false);
      setPendingFileForMetadata(null);
      setPendingMetadataFileId('');
      setError(null);
    } finally {
      setIsMetadataLoading(false);
    }
  };

  const startOntologyRegistration = async (file) => {
    const fileId = file.fileId;
    if (file.pendingMetadata || !file.ontologyName || !file.prefix || !file.generationType) {
      setMetadataFormPrefill({
        ontologyName: file.ontologyName || '',
        prefix: file.prefix || '',
        description: file.description || '',
        generationType: file.generationType || '',
        schemaType: file.schemaType || 'schema',
      });
      setPendingFileForMetadata(file.fileObj);
      setPendingMetadataFileId(fileId);
      setShowMetadataForm(true);
      setError(`Complete ontology details for ${file.name} before starting.`);
      return;
    }

    try {
      setStartedFiles(prev => new Set([...prev, fileId]));
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          stage: 'upload',
          backendStage: 'upload',
          progress: 15,
          status: 'processing',
          message: `Registering ontology '${file.ontologyName}'...`,
          error: false,
        }
      }));

      const uploadData = await API_METHODS.ontology.upload(file.fileObj, {
        ontologyName: file.ontologyName,
        prefix: file.prefix,
        description: file.description || '',
        generationType: file.generationType,
        schemaType: file.schemaType || 'schema',
        fileType: file.fileType,
      });
      const uploadDataBody = uploadData.data || uploadData;

      setFiles(prev => prev.map(f => (
        f.fileId === fileId
          ? {
              ...f,
              taskId: uploadDataBody.task_id,
              ontologyId: uploadDataBody.ontology_id,
              sourceNamespace: uploadDataBody.source_namespace || uploadDataBody.target_namespace || '',
              baseUri: uploadDataBody.base_uri || '',
            }
          : f
      )));
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          taskId: uploadDataBody.task_id,
          stage: 'verify',
          backendStage: 'verify',
          progress: 100,
          status: 'completed',
          committed: true,
          message: `Ontology '${file.ontologyName}' uploaded and registered`,
          stats: {
            entities_found: uploadDataBody.nodes_merged ?? null,
            relationships_found: null,
          },
          error: false,
          completedAt: new Date().toLocaleTimeString(),
        }
      }));
      setError(null);
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          stage: 'error',
          backendStage: 'error',
          progress: 0,
          status: 'failed',
          message: String(detail),
          error: true,
        }
      }));
      setStartedFiles(prev => {
        const next = new Set(prev);
        next.delete(fileId);
        return next;
      });
      setError(`Error uploading ontology: ${detail}`);
    }
  };


  // Map file extension to ontology id (dynamic, not hardcoded)
  const getOntologyForFile = (fileName) => {
    const fileType = inferFileTypeFromExtension(fileName);

    if (fileType === 'step') return 'step_ap242_mbd3d';
    if (fileType === 'ontology') return '';
    if (fileType === 'json' || fileType === 'xml') return '';

    return '';
  };

  const getAlignmentPolicy = (fileName) => {
    const fileType = inferFileTypeFromExtension(fileName);
    const isStep = fileType === 'step';
    const isDirectOntology = fileType === 'ontology';

    return {
      fileType,
      isStep,
      isDirectOntology,
      forcedMapping: isStep ? 'step_ap242_mbd3d' : '',
    };
  };

  const startDocumentPipeline = async (file) => {
    const workflow = workflowOptions.find(w => w.id === (file.workflowId || selectedWorkflow)) || resolveWorkflow(file.workflowId || selectedWorkflow);
    if (workflow?.status !== 'available') {
      setError(`${getWorkflowDisplayName(file.workflowId || selectedWorkflow)} is not connected to backend services yet.`);
      return;
    }

    const fileId = file.fileId;
    try {
      setStartedFiles(prev => new Set([...prev, fileId]));
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          stage: 'upload',
          backendStage: 'upload',
          progress: 5,
          status: 'processing',
          message: 'Uploading document to unstructured pipeline...',
          lastUpdatedAt: new Date().toISOString(),
        },
      }));

      const safeIndexBase = String(file?.name || 'document').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 48) || 'document';
      const response = await API_METHODS.document.upload([file.fileObj], { index_name: safeIndexBase + '_index' });
      const result = response.data || response;
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          stage: 'verify',
          backendStage: 'indexed',
          progress: 100,
          status: result?.status === 'success' || result?.success !== false ? 'completed' : 'completed',
          message: result?.message || 'Document indexed for GraphRAG search.',
          stats: {
            entities_found: result?.processed_documents ?? result?.documents_processed ?? result?.total_documents ?? 1,
            relationships_found: result?.chunks_created ?? result?.total_chunks ?? 0,
          },
          result,
          completedAt: new Date().toLocaleTimeString(),
          completedAtIso: new Date().toISOString(),
          lastUpdatedAt: new Date().toISOString(),
        },
      }));
      setError(null);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          ...(prev[fileId] || {}),
          stage: 'error',
          backendStage: 'error',
          progress: 0,
          status: 'failed',
          message: String(detail),
          error: true,
        },
      }));
      setStartedFiles(prev => {
        const next = new Set(prev);
        next.delete(fileId);
        return next;
      });
      setError(`Error processing document: ${detail}`);
    }
  };
  const startImport = async (file) => {
    const workflow = workflowOptions.find(w => w.id === (file.workflowId || selectedWorkflow)) || resolveWorkflow(file.workflowId || selectedWorkflow);
    if (workflow?.status !== 'available') {
      setError(`${getWorkflowDisplayName(file.workflowId || selectedWorkflow)} is not connected to backend services yet. Review the workflow plan, then choose an available workflow to run.`);
      return;
    }

    const fileId = file.fileId;

    try {
      const formData = new FormData();
      formData.append('file', file.fileObj);

      const policy = getAlignmentPolicy(file.name);
      let ontologyToUse = getOntologyForFile(file.name);

      if (policy.isStep) {
        ontologyToUse = policy.forcedMapping;
      }

      setStartedFiles(prev => new Set([...prev, fileId]));
      setPipelineStatus(prev => ({ ...prev, [fileId]: { stage: 'upload', progress: 0, message: 'Uploading...' } }));

      if (ontologyToUse) {
        formData.append('ontology_id', ontologyToUse);
      }

      const uploadData = await apiClient.post(API.import.upload, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: getImportTimeoutMs(),
      });
      const taskId = (uploadData.data || uploadData).task_id;

      if (!taskId) {
        throw new Error('Server did not return a task ID. Upload may have failed.');
      }

      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: { 
          ...prev[fileId],
          taskId,
          stage: 'convert',
          progress: 10,
          message: policy.isStep ? `Converting with AP242 context: ${ontologyToUse}` : 'Converting file...'
        }
      }));

      // Give backend a brief moment to initialize task state before first poll.
      await new Promise(resolve => setTimeout(resolve, 300));
      await pollPipelineProgress(taskId, fileId);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: { 
          ...prev[fileId], 
          stage: 'error', 
          message: String(detail),
          error: true 
        }
      }));
      setStartedFiles(prev => {
        const next = new Set(prev);
        next.delete(fileId);
        return next;
      });
    }
  };

  useEffect(() => {
    if (showMetadataForm || isMetadataLoading) return;
    if (!pendingMetadataQueue.length) return;

    const nextFileId = pendingMetadataQueue[0];
    const nextFile = files.find(f => f.fileId === nextFileId);
    if (!nextFile) {
      setPendingMetadataQueue(prev => prev.filter(id => id !== nextFileId));
      return;
    }

    setMetadataFormPrefill({
      ontologyName: nextFile.ontologyName || '',
      prefix: nextFile.prefix || '',
      description: nextFile.description || '',
      generationType: nextFile.generationType || '',
      schemaType: nextFile.schemaType || 'schema',
    });
    setPendingFileForMetadata(nextFile.fileObj);
    setPendingMetadataFileId(nextFileId);
    setShowMetadataForm(true);
  }, [files, isMetadataLoading, pendingMetadataQueue, showMetadataForm]);

  const pollPipelineProgress = async (taskId, fileId) => {
    const pollerKey = `${taskId}:${fileId}`;
    if (activePollersRef.current.has(pollerKey)) {
      return;
    }
    activePollersRef.current.add(pollerKey);
    const maxAttempts = 600;
    let attempts = 0;

    const poll = async () => {
      try {
        const statusUrl = buildUrl(replaceParams(API.import.status, { task_id: taskId }));
        const res = await apiClient.get(statusUrl);
        const data = res.data;

        // Task creation is async in backend; treat not_found as transient instead of hard failure.
        if (data?.status === 'not_found') {
          if (attempts < maxAttempts) {
            attempts++;
            setPipelineStatus(prev => ({
              ...prev,
              [fileId]: {
                ...(prev[fileId] || {}),
                taskId,
                stage: 'upload',
                progress: 5,
                status: 'processing',
                message: 'Initializing task...',
                lastUpdatedAt: new Date().toISOString()
              }
            }));
            setTimeout(poll, 2000);
          }
          return;
        }

        const mappedStage = backendToFrontendStage[data.current_stage] || data.current_stage || 'upload';

        // F-NEW-8: normalize stats — backend parsers use different key names for entity/rel counts.
        const rawStats = data.stats || {};
        const entities_found =
          rawStats.entities_found ??
          rawStats.row_count ??
          rawStats.total_items ??
          rawStats.element_count;
        const relationships_found =
          rawStats.relationships_found ??
          rawStats.relationship_count;
        const normalizedStats = {
          ...rawStats,
          entities_found,
          relationships_found,
        };
        
        const shaclConforms = data?.result?.shacl_conforms ?? data?.shacl_conforms ?? null;
        const shaclFile = data?._shacl_file ?? data?.result?._shacl_file ?? null;

        setPipelineStatus(prev => ({
          ...prev,
          [fileId]: {
            ...(prev[fileId] || {}),
            taskId,
            stage: mappedStage,
            backendStage: data.current_stage,
            progress: data.progress,
            message: data.message,
            stats: normalizedStats,
            status: data.status,
            committing: typeof data.committing === 'boolean'
              ? data.committing
              : ((data.current_stage === 'ingest' || !!data.commit_phase) && data.status !== 'completed' && data.status !== 'failed'),
            error: data.error ? true : false,
            completedAt: data.status === 'completed' ? new Date().toLocaleTimeString() : null,
            completedAtIso: data.status === 'completed' ? new Date().toISOString() : (prev[fileId]?.completedAtIso || null),
            lastUpdatedAt: new Date().toISOString(),
            commitPhase: data.commit_phase || null,
            batchProgress: data.batch_progress || null,
            commitMetrics: data.commit_metrics || null,
            shaclConforms,
            shaclFile,
            artifact_manifest: data.artifact_manifest,
            workflow_id: data.workflow_id,
            resumeExpired: false,
          }
        }));

        // Auto-set preview data when preview/verify stage or completed is reached
        if (data.current_stage === 'preview' || data.current_stage === 'verify' || data.status === 'completed') {
          const statusPreview = {
            ...data,
            row_count: normalizedStats.row_count ?? normalizedStats.entities_found ?? 0,
            columns: normalizedStats.columns || [],
            sample_rows: [],
            auto_schema: data.auto_schema || {},
          };
          setPreviewData(statusPreview);
          // Fetch actual preview rows from the preview endpoint
          try {
            const previewUrl = buildUrl(replaceParams(API.import.preview, { task_id: taskId }));
            const previewRes = await apiClient.get(previewUrl);
            if (previewRes.data) {
              // F2 FIX: spread preview endpoint fields directly onto previewData so the
              // modal can read row_count / columns / sample_rows / auto_schema at the top level.
              // Previously they were nested under .preview which the modal never read.
              setPreviewData(prev => ({
                ...prev,
                row_count:   previewRes.data.row_count   ?? prev?.row_count   ?? 0,
                columns:     previewRes.data.columns     || prev?.columns     || [],
                sample_rows: previewRes.data.sample_rows || prev?.sample_rows || [],
                auto_schema: previewRes.data.auto_schema || prev?.auto_schema || {},
              }));
            }
          } catch (_) { /* preview is optional — continue without it */ }
        }

        if (data.status === 'completed' || data.status === 'failed') {
          activePollersRef.current.delete(pollerKey);
          return;
        }

        if (attempts < maxAttempts) {
          attempts++;
          const nextDelay =
            data.current_stage === 'ingest' || data.commit_phase
              ? 1500
              : 2500;
          setTimeout(poll, nextDelay);
        } else {
          activePollersRef.current.delete(pollerKey);
        }
      } catch (err) {
        if (attempts < maxAttempts) {
          attempts++;
          setPipelineStatus(prev => ({
            ...prev,
            [fileId]: {
              ...(prev[fileId] || {}),
              taskId,
              message: `Waiting for service response... ${err.message}`,
              lastUpdatedAt: new Date().toISOString(),
            }
          }));
          setTimeout(poll, 3000);
          return;
        }
        activePollersRef.current.delete(pollerKey);
        setPipelineStatus(prev => ({
          ...prev,
          [fileId]: { ...prev[fileId], stage: 'error', message: err.message, error: true }
        }));
      }
    };

    poll();
  };

  useEffect(() => {
    if (!didRestoreJobsRef.current || resumedPersistedJobsRef.current) return;
    const resumableJobs = [];
    const staleFileIds = [];

    files.forEach((file) => {
      const status = pipelineStatus[file.fileId];
      if (!file?.taskId || !startedFiles.has(file.fileId) || !status) return;
      if (isResumablePersistedJob(file, status)) {
        resumableJobs.push(file);
        return;
      }
      if (!isTerminalPipelineStatus(status)) {
        staleFileIds.push(file.fileId);
      }
    });

    resumedPersistedJobsRef.current = true;

    if (staleFileIds.length) {
      setPipelineStatus((prev) => {
        const next = { ...prev };
        staleFileIds.forEach((fileId) => {
          next[fileId] = {
            ...(next[fileId] || {}),
            committing: false,
            resumeExpired: true,
            message: 'Previous session found. Re-run status or restart this file to continue safely.',
            lastUpdatedAt: new Date().toISOString(),
          };
        });
        return next;
      });
    }

    resumableJobs.forEach((file) => {
      pollPipelineProgress(file.taskId, file.fileId);
    });
  }, [files, pipelineStatus, startedFiles]);

  const startAllImports = async () => {
    const workflow = workflowOptions.find(w => w.id === selectedWorkflow) || resolveWorkflow(selectedWorkflow);
    if (workflow?.status !== 'available') {
      setError(`${getWorkflowDisplayName(selectedWorkflow)} is not connected to backend services yet. Use Import instance graph or Create ontology for current execution.`);
      return;
    }

    const filesToImport = files.filter(f => {
      if (startedFiles.has(f.fileId)) return false;
      if ((f.workflowId || selectedWorkflow) !== selectedWorkflow) return false;
      if (selectedWorkflow === 'instance.import') {
        const policy = getAlignmentPolicy(f.name);
        return !policy.isDirectOntology;
      }
      if (selectedWorkflow === 'document.unstructured') {
        return inferFileTypeFromExtension(f.name) === 'document';
      }
      if (selectedWorkflow === 'architecture.archimate') {
        return inferFileTypeFromExtension(f.name) === 'archimate' || getFileExtensionFromName(f.name) === '.xml';
      }
      if (selectedWorkflow === 'ontology.create') {
        return !f.pendingMetadata;
      }
      return false;
    });
    if (filesToImport.length === 0) {
      setError(selectedWorkflow === 'ontology.create'
        ? 'Complete ontology details before starting registration.'
        : 'All files have already been started');
      return;
    }

    for (const file of filesToImport) {
      if (selectedWorkflow === 'ontology.create') {
        startOntologyRegistration(file);
      } else if (selectedWorkflow === 'document.unstructured') {
        startDocumentPipeline(file);
      } else {
        startImport(file);
      }
    }
  };

  const runSelectedWorkflow = async () => {
    if (isImportWorkflow(selectedWorkflow)) {
      startAllImports();
      return;
    }
    if (workflowBlockReason) {
      setError(workflowBlockReason);
      return;
    }

    const selectedImportManifest = selectedImportArtifactEntry?.artifactManifest || null;
    const payload = {
      ontology_id: workflowOntologyId,
      source_ontology_id: workflowOntologyId,
      import_artifact_manifest: selectedImportManifest,
      import_source_file_id: selectedImportArtifactEntry?.fileId || null,
      apply_links: selectedWorkflow === 'instance.link' ? workflowApplyLinks : false,
    };
    if (selectedWorkflow === 'ontology.merge') {
      payload.target_ontology_id = workflowTargetOntologyId;
    }

    setWorkflowLoading(true);
    setWorkflowRun(null);
    setError(null);
    try {
      const response = await API_METHODS.workflow.execute(selectedWorkflow, payload);
      setWorkflowRun(response.data || response);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
      setError(String(detail));
    } finally {
      setWorkflowLoading(false);
    }
  };

  const runNeo4jOntologyMerge = async () => {
    if (!workflowOntologyId) {
      setError('Select a source ontology before merging.');
      return;
    }
    if (!workflowTargetOntologyId) {
      setError('Select a target ontology before merging.');
      return;
    }
    if (workflowTargetOntologyId === workflowOntologyId) {
      setError('Choose two different ontologies for merge.');
      return;
    }

    setWorkflowLoading(true);
    setWorkflowRun(null);
    setError(null);
    try {
      const response = await API_METHODS.ontology.merge(workflowOntologyId, workflowTargetOntologyId, { dry_run: false });
      setWorkflowRun({
        workflow_id: 'ontology.merge.commit',
        status: 'completed',
        result: response.data || response,
      });
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
      setError(String(detail));
    } finally {
      setWorkflowLoading(false);
    }
  };

  const commitImport = async (taskId) => {
    // ── Pre-commit check ────────────────────────────────────────────────────
    // Show a quick checking state in the modal before closing it
    try {
      const checkRes = await apiClient.get(
        buildUrl(replaceParams(API.import.preCommit, { task_id: taskId })),
        { timeout: 300000 }
      );
      const check = checkRes.data || {};
      if (!check.ready) {
        // Don't close the modal — show the blocking reason
        const reason = check.reason || 'Pre-commit check failed.';
        const neo4jOk = check.checks?.neo4j?.ok;
        const taskOk  = check.checks?.task?.ok;
        let msg = `Cannot commit: ${reason}`;
        if (!neo4jOk) msg += '\n\nNeo4j is unreachable — check your database connection.';
        if (!taskOk)  msg += `\n\nTask state: ${check.checks?.task?.status}`;
        setError(msg);
        return; // abort — modal stays open
      }
      // All checks passed — show row count in a brief toast before proceeding
      const rowCount = check.checks?.task?.rows;
      if (rowCount) setError(null); // clear any prior errors
    } catch (checkErr) {
      // If the pre-check itself fails, block the commit so we do not load blindly.
      console.warn('[pre-commit] check failed:', checkErr.message);
      setPreCheck({
        loading: false,
        ready: false,
        checks: { neo4j: { ok: false }, task: { ok: false } },
        reason: checkErr.message || 'Pre-commit check failed.',
      });
      return;
    }

    // Close the review modal immediately — don't make the user wait 2-3 min
    setConfirmingImport(null);

    // Mark as "loading to Neo4j" in the file card right away
    setPipelineStatus(prev => {
      const updated = { ...prev };
      for (const [fid, status] of Object.entries(updated)) {
        if (status.taskId === taskId) {
          updated[fid] = {
            ...status,
            committing: true,
            progress: 80,
            commitPhase: 'queued',
            message: 'Queued for Neo4j commit. You can stay on this page while batches continue.',
            lastUpdatedAt: new Date().toISOString(),
          };
        }
      }
      return updated;
    });

    // Run the actual commit in background — UI stays responsive
    const commitUrl = buildUrl(replaceParams(API.import.commit, { task_id: taskId }));
    const commitTimeoutMs = getImportTimeoutMs();
    const fileId = Object.entries(pipelineStatus).find(([, status]) => status.taskId === taskId)?.[0] || taskId;
    fetch(commitUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(commitTimeoutMs),
    })
      .then(async commitRes => {
        if (!commitRes.ok) {
          const errBody = await commitRes.json().catch(() => ({}));
          const detail = errBody?.detail || errBody?.message || errBody?.error || commitRes.statusText;
          throw new Error(detail);
        }
        const commitData = await commitRes.json().catch(() => ({}));
        const commitResult = commitData.result || {};
        if (commitData.queued) {
          setPipelineStatus(prev => {
            const updated = { ...prev };
            for (const [fid, status] of Object.entries(updated)) {
              if (status.taskId === taskId) {
                updated[fid] = {
                  ...status,
                  committing: true,
                  stage: 'load',
                  backendStage: 'ingest',
                  progress: Math.max(status.progress || 80, 80),
                  commitPhase: 'queued',
                  message: commitData.message || 'Neo4j commit queued in background. The loader will keep polling until the write finishes.',
                  lastUpdatedAt: new Date().toISOString(),
                };
              }
            }
            return updated;
          });
          await pollPipelineProgress(taskId, fileId);
          return;
        }
        // Mark complete
        setPipelineStatus(prev => {
          const updated = { ...prev };
          for (const [fid, status] of Object.entries(updated)) {
            if (status.taskId === taskId) {
              const entityCount =
                commitResult.nodes_created ??
                status.stats?.row_count ??
                status.stats?.entities_found;
              const relationshipCount =
                commitResult.relationships_created ??
                status.stats?.relationships_found;
              updated[fid] = {
                ...status,
                stage: 'load',
                backendStage: 'ingest',
                progress: 100,
                status: 'completed',
                message: 'Import completed successfully',
                committed: true,
                committing: false,
                commitPhase: 'complete',
                completedAt: new Date().toLocaleTimeString(),
                completedAtIso: new Date().toISOString(),
                lastUpdatedAt: new Date().toISOString(),
                stats: {
                  ...status.stats,
                  entities_found: entityCount,
                  relationships_found: relationshipCount,
                  instance_links_created: commitResult.instance_links_created,
                  ontology_classes_matched: commitResult.ontology_classes_matched,
                },
              };
            }
          }
          return updated;
        });
        setError(null);
      })
      .catch(err => {
        // Mark as error in the file card
        setPipelineStatus(prev => {
          const updated = { ...prev };
          for (const [fid, status] of Object.entries(updated)) {
            if (status.taskId === taskId) {
              updated[fid] = {
                ...status,
                committing: false,
                commitPhase: 'error',
                commitError: err.message,
                lastUpdatedAt: new Date().toISOString(),
              };
            }
          }
          return updated;
        });
        setError(`Commit failed: ${err.message}`);
      });
  };

  const removeFile = (fileId) => {
    const fileStatus = pipelineStatus[fileId];
    if (fileStatus?.taskId) {
      activePollersRef.current.delete(`${fileStatus.taskId}:${fileId}`);
    }

    setPendingMetadataQueue(prev => prev.filter(id => id !== fileId));
    if (pendingMetadataFileId === fileId) {
      setShowMetadataForm(false);
      setPendingFileForMetadata(null);
      setPendingMetadataFileId('');
      setMetadataFormPrefill(null);
    }
    
    // Cancel task if in progress
    if (fileStatus?.taskId && fileStatus?.status === 'processing') {
      apiClient.post(replaceParams(API.import.cancel, { task_id: fileStatus.taskId }), {})
        .catch(err => console.warn('Cancel failed:', err));
    }

    setFiles(prev => prev.filter(f => f.fileId !== fileId));
    setStartedFiles(prev => {
      const updated = new Set(prev);
      updated.delete(fileId);
      return updated;
    });
  };

  const getStatusBadge = (stage, progress, error, backendStage, committing, commitError, commitPhase) => {
    if (committing || (commitPhase && commitPhase !== 'complete' && commitPhase !== 'error')) {
      const phaseLabel = getCommitPhaseLabel(commitPhase);
      return { text: phaseLabel ? `Loading · ${phaseLabel}` : 'Loading to Neo4j...', bg: '#FFF8E1', color: '#F57F17' };
    }
    if (commitError || commitPhase === 'error') {
      return { text: 'Commit Retry Needed', bg: '#FFEBEE', color: C.red };
    }
    if (error) {
      return { text: 'Attention Needed', bg: '#FFEBEE', color: C.red };
    }
    if (backendStage === 'preview' || backendStage === 'verify' || stage === 'validate' || stage === 'verify') {
      return { text: 'Ready to Load', bg: '#E8F5E9', color: C.green };
    }
    if (progress === 100) {
      return { text: 'Complete', bg: '#E8F5E9', color: C.green };
    }
    if (progress > 0) {
      return { text: 'Processing', bg: '#E3F2FD', color: C.primary };
    }
    return { text: 'Pending', bg: C.bg, color: C.textMuted };
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const getImportTimeoutMs = () => {
    return 900 * 1000;
  };

  const getCommitPhaseLabel = (phase) => {
    switch (phase) {
      case 'prepare':
        return 'Preparing';
      case 'nodes':
        return 'Writing entities';
      case 'relationships':
        return 'Writing relationships';
      case 'ontology-linking':
        return 'Linking ontology';
      case 'verification':
        return 'Verifying';
      case 'complete':
        return 'Complete';
      case 'queued':
        return 'Queued';
      case 'error':
        return 'Attention needed';
      default:
        return '';
    }
  };

  const formatBatchProgress = (batchProgress) => {
    if (!batchProgress?.total_batches) return '';
    const scope = batchProgress.scope ? `${batchProgress.scope} ` : '';
    return `${scope}${batchProgress.batch_index || 0}/${batchProgress.total_batches}`;
  };

  const downloadOntologyExport = async (taskId, format = 'ttl') => {
    if (!taskId) return;
    try {
      const response = await API_METHODS.import.exportOWL(taskId, format);
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data]);
      const disposition = response.headers?.['content-disposition'] || '';
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match?.[1] || `ontology_${taskId}.${format}`;
      const url = window.URL.createObjectURL(blob);
      const anchorEl = document.createElement('a');
      anchorEl.href = url;
      anchorEl.download = filename;
      document.body.appendChild(anchorEl);
      anchorEl.click();
      anchorEl.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || 'Export failed';
      setError(String(detail));
    }
  };

  const isCommitInFlight = (status = {}) =>
    !!(status.committing || (status.commitPhase && status.commitPhase !== 'complete' && status.commitPhase !== 'error'));

  const isReadyToLoad = (status = {}) =>
    !!(
      !status.error &&
      !status.committed &&
      (status.backendStage === 'preview' || status.backendStage === 'verify' || status.stage === 'validate' || status.stage === 'verify')
    );

  const isProcessingJob = (status = {}) =>
    !!(
      !status.error &&
      !status.commitError &&
      !isCommitInFlight(status) &&
      !isReadyToLoad(status) &&
      !isTerminalPipelineStatus(status)
    );

  const activeWorkflow = useMemo(
    () => workflowOptions.find(w => w.id === selectedWorkflow) || workflowOptions[0] || resolveWorkflow(selectedWorkflow),
    [workflowOptions, selectedWorkflow]
  );
  const groupedWorkflows = useMemo(() => {
    const groups = new Map();
    workflowOptions.forEach((workflow) => {
      const groupName = workflow.category || 'Other';
      if (!groups.has(groupName)) groups.set(groupName, []);
      groups.get(groupName).push(workflow);
    });
    return Array.from(groups.entries()).map(([category, items]) => ({ category, items }));
  }, [workflowOptions]);
  const primaryWorkflows = useMemo(
    () => workflowOptions.filter((workflow) => PRIMARY_WORKFLOW_IDS.has(workflow.id)),
    [workflowOptions]
  );
  const advancedWorkflows = useMemo(
    () => workflowOptions.filter((workflow) => !PRIMARY_WORKFLOW_IDS.has(workflow.id)),
    [workflowOptions]
  );
  const fallbackWorkflow = useMemo(
    () => activeWorkflow || resolveWorkflow(selectedWorkflow) || {
      id: selectedWorkflow || 'workflow',
      title: getWorkflowDisplayName(selectedWorkflow),
      label: getWorkflowDisplayName(selectedWorkflow),
      description: 'Select a workflow to continue.',
      prerequisite: '',
      execution: '',
      icon: Play,
    },
    [activeWorkflow, selectedWorkflow]
  );
  const activePipelineStages = useMemo(
    () => buildWorkflowStages(fallbackWorkflow),
    [fallbackWorkflow]
  );
  const fileStatusIndex = useMemo(() => {
    const index = new Map();
    files.forEach((file) => {
      index.set(file.fileId, pipelineStatus[file.fileId] || { stage: 'upload', progress: 0 });
    });
    return index;
  }, [files, pipelineStatus]);
  const contextFile = useMemo(
    () => files.find(f => !startedFiles.has(f.fileId)) || files[0] || pendingFileForMetadata,
    [files, startedFiles, pendingFileForMetadata]
  );
  const recommendedWorkflowId = contextFile ? recommendWorkflowForFile(contextFile.name) : selectedWorkflow;
  const canRunSelectedWorkflow = fallbackWorkflow.status === 'available';
  const pendingFileCount = useMemo(
    () => files.reduce((count, f) => count + (startedFiles.has(f.fileId) ? 0 : 1), 0),
    [files, startedFiles]
  );
  const workflowRequiresOntology = !isImportWorkflow(selectedWorkflow);
  const workflowRequiresTargetOntology = selectedWorkflow === 'ontology.merge';
  const workflowRequiresImportArtifact = selectedWorkflow === 'instance.link';
  const importArtifactCandidates = useMemo(
    () => files
      .map((file) => {
        const status = fileStatusIndex.get(file.fileId) || {};
        const artifactManifest = file.artifact_manifest || file.artifactManifest || file.manifest || status.artifact_manifest || null;
        const isImportedInstance = (file.workflowId || selectedWorkflow) === 'instance.import';
        const isCompletedArtifact = status.committed || status.status === 'completed' || status.progress === 100;
        if (!artifactManifest || !isImportedInstance || !isCompletedArtifact) return null;
        return {
          fileId: file.fileId,
          name: file.name,
          label: `${file.name} (${status.completedAt || file.createdAt || 'available'})`,
          artifactManifest,
          status,
        };
      })
      .filter(Boolean),
    [fileStatusIndex, files, selectedWorkflow]
  );
  const selectedImportArtifactEntry = useMemo(
    () => importArtifactCandidates.find((entry) => entry.fileId === workflowSourceFileId) || importArtifactCandidates[0] || null,
    [importArtifactCandidates, workflowSourceFileId]
  );
  const workflowActionLabel = selectedWorkflow === 'ontology.merge'
    ? 'Review merge plan'
    : selectedWorkflow === 'instance.link'
      ? 'Preview bridge'
      : selectedWorkflow === 'ontology.create'
        ? 'Register ontology'
        : 'Run workflow';
  const workflowBlockReason = (() => {
    if (!canRunSelectedWorkflow) {
      return `${fallbackWorkflow.title} is not connected to backend services yet.`;
    }
    if (isImportWorkflow(selectedWorkflow)) {
      if (pendingFileCount === 0) return 'Add at least one new file to start this workflow.';
      return '';
    }
    if (workflowRequiresImportArtifact && !selectedImportArtifactEntry) {
      return 'Select one completed instance import artifact before running the bridge workflow.';
    }
    if (workflowRequiresOntology && !workflowOntologyId) {
      return selectedWorkflow === 'ontology.merge' ? 'Select a source ontology.' : 'Select an ontology.';
    }
    if (workflowRequiresTargetOntology && !workflowTargetOntologyId) {
      return 'Select a target ontology.';
    }
    if (workflowRequiresTargetOntology && workflowTargetOntologyId === workflowOntologyId) {
      return 'Choose two different ontologies for merge.';
    }
    return '';
  })();
  useEffect(() => {
    if (selectedWorkflow !== 'instance.link') return;
    if (importArtifactCandidates.length === 0) {
      if (workflowSourceFileId) setWorkflowSourceFileId('');
      return;
    }
    const stillValid = importArtifactCandidates.some((entry) => entry.fileId === workflowSourceFileId);
    if (!workflowSourceFileId || !stillValid) {
      setWorkflowSourceFileId(importArtifactCandidates[0].fileId);
    }
  }, [importArtifactCandidates, selectedWorkflow, workflowSourceFileId]);

  const activeProcessingCount = useMemo(
    () => files.reduce((count, file) => {
      const status = fileStatusIndex.get(file.fileId) || {};
      if (!startedFiles.has(file.fileId)) return count;
      if (status.error || status.commitError || status.resumeExpired) return count;
      if (status.committed || status.status === 'completed' || status.progress === 100) return count;
      return count + 1;
    }, 0),
    [files, startedFiles, fileStatusIndex]
  );
  const jobSummary = useMemo(() => {
    return files.reduce((summary, file) => {
      const status = fileStatusIndex.get(file.fileId) || {};
      if (!startedFiles.has(file.fileId)) {
        summary.pending += 1;
        return summary;
      }
      if (status.error || status.commitError || status.status === 'failed' || status.resumeExpired) {
        summary.failed += 1;
        return summary;
      }
      if (status.committed || status.status === 'completed' || status.progress === 100) {
        summary.completed += 1;
        return summary;
      }
      summary.active += 1;
      return summary;
    }, { active: 0, completed: 0, failed: 0, pending: 0 });
  }, [files, startedFiles, fileStatusIndex]);
  const activeJobs = useMemo(
    () => files
      .map((file) => ({ file, status: fileStatusIndex.get(file.fileId) || {} }))
      .filter(({ file, status }) => startedFiles.has(file.fileId) && status.status !== 'completed' && status.status !== 'failed'),
    [files, fileStatusIndex, startedFiles]
  );
  const stageFileCounts = useMemo(() => {
    const counts = new Map(activePipelineStages.map(stage => [stage.id, 0]));
    files.forEach((file) => {
      const status = fileStatusIndex.get(file.fileId) || {};
      const currentStage = status.stage || 'upload';
      const frontendStage = backendToFrontendStage[currentStage] || currentStage;
      activePipelineStages.forEach((stage) => {
        if (stage.backendIds.includes(currentStage) || stage.backendIds.includes(frontendStage)) {
          counts.set(stage.id, (counts.get(stage.id) || 0) + 1);
        }
      });
    });
    return counts;
  }, [activePipelineStages, fileStatusIndex, files]);
  const selectedStageFiles = useMemo(() => {
    const stage = activePipelineStages.find(s => s.id === selectedStage);
    if (!stage) return [];
    return files.filter((f) => {
      const status = fileStatusIndex.get(f.fileId) || {};
      const currentStage = status.stage || 'upload';
      const frontendStage = backendToFrontendStage[currentStage] || currentStage;
      return stage.backendIds.includes(currentStage) || stage.backendIds.includes(frontendStage);
    });
  }, [activePipelineStages, fileStatusIndex, files, selectedStage]);
  const activePipelineStageIds = useMemo(
    () => activePipelineStages.map(stage => stage.id).join('|'),
    [activePipelineStages]
  );

  useEffect(() => {
    if (!activePipelineStages.some(stage => stage.id === selectedStage)) {
      setSelectedStage(activePipelineStages[0]?.id || 'upload');
    }
  }, [activePipelineStageIds, activePipelineStages, selectedStage]);

  useEffect(() => {
    if (!PRIMARY_WORKFLOW_IDS.has(selectedWorkflow)) {
      setShowAdvancedWorkflows(true);
    }
  }, [selectedWorkflow]);

  return (
    <div style={{ background: C.bg, minHeight: '100%', padding: 0, boxSizing: 'border-box' }}>
      {/* Ontology Metadata Form Modal */}
      {showMetadataForm && (
        <OntologyMetadataForm
          selectedFile={pendingFileForMetadata}
          onSubmit={handleMetadataSubmit}
          onCancel={() => {
            if (pendingMetadataFileId) {
              setPendingMetadataQueue(prev => prev.filter(id => id !== pendingMetadataFileId));
              setPipelineStatus(prev => ({
                ...prev,
                [pendingMetadataFileId]: {
                  ...(prev[pendingMetadataFileId] || {}),
                  stage: 'upload',
                  backendStage: 'upload',
                  progress: 0,
                  status: 'pending',
                  message: 'Ontology details required before registration.',
                  error: false,
                }
              }));
            }
            setMetadataFormPrefill(null);
            setShowMetadataForm(false);
            setPendingFileForMetadata(null);
            setPendingMetadataFileId('');
          }}
          initialValues={metadataFormPrefill}
          isLoading={isMetadataLoading}
          formTitle="Ontology Metadata"
          ontologyNamePlaceholder="e.g., Product Model"
          prefixPlaceholder="e.g., myprefix"
        />
      )}

      {/* Compact workflow selector */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        padding: '8px',
        marginBottom: '8px',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          flexWrap: 'wrap',
          marginBottom: '8px',
        }}>
          <span style={{
            fontSize: '10px',
            fontWeight: '800',
            color: C.textPrimary,
            marginRight: '2px',
          }}>
            Workflow
          </span>
          {primaryWorkflows.map((workflow) => {
            const Icon = workflow.icon;
            const isActive = workflow.id === selectedWorkflow;
            const isRecommended = workflow.id === recommendedWorkflowId;
            return (
              <button
                key={workflow.id}
                type="button"
                onClick={() => setSelectedWorkflow(workflow.id)}
                style={{
                  border: `1px solid ${isActive ? C.primary : C.border}`,
                  background: isActive ? C.primary : C.bg,
                  color: isActive ? '#fff' : C.textPrimary,
                  borderRadius: '4px',
                  padding: '5px 8px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  minHeight: '30px',
                }}
                title={workflow.description}
              >
                <Icon size={13} strokeWidth={2.4} />
                <span style={{ fontSize: '10px', fontWeight: '800', whiteSpace: 'nowrap' }}>
                  {workflow.title}
                </span>
                {isRecommended && (
                  <span style={{
                    fontSize: '8px',
                    fontWeight: '800',
                    color: isActive ? '#fff' : C.primary,
                    background: isActive ? 'rgba(255,255,255,0.16)' : '#FFFFFF',
                    border: `1px solid ${isActive ? 'rgba(255,255,255,0.26)' : C.primaryLight}`,
                    borderRadius: '999px',
                    padding: '1px 5px',
                  }}>
                    Suggested
                  </span>
                )}
              </button>
            );
          })}
          {advancedWorkflows.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAdvancedWorkflows((open) => !open)}
              style={{
                background: 'transparent',
                border: `1px solid ${C.border}`,
                borderRadius: '4px',
                padding: '5px 8px',
                fontSize: '10px',
                fontWeight: '800',
                color: C.textPrimary,
                cursor: 'pointer',
                minHeight: '30px',
              }}
            >
              {showAdvancedWorkflows ? 'Hide advanced' : `Advanced (${advancedWorkflows.length})`}
            </button>
          )}
        </div>
        {showAdvancedWorkflows && (
          <>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
        }}>
          <label htmlFor="import-workflow-select" style={{
            fontSize: '10px',
            fontWeight: '700',
            color: C.textPrimary,
            whiteSpace: 'nowrap',
          }}>
            Advanced workflow
          </label>
          <select
            id="import-workflow-select"
            value={selectedWorkflow}
            onChange={(e) => setSelectedWorkflow(e.target.value)}
            style={{
              minWidth: '220px',
              flex: '1 1 260px',
              maxWidth: '460px',
              padding: '5px 8px',
              fontSize: '11px',
              border: `1px solid ${C.borderDark}`,
              borderRadius: '4px',
              background: C.bg,
              color: C.textPrimary,
            }}
          >
            {groupedWorkflows.map(group => (
              <optgroup key={group.category} label={group.category}>
                {group.items.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.title}{option.id === recommendedWorkflowId ? ' - recommended' : ''}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {(() => {
            const Icon = fallbackWorkflow.icon;
            return (
              <div style={{
                width: '24px',
                height: '24px',
                borderRadius: '6px',
                background: C.primaryLight,
                color: C.primary,
                display: 'grid',
                placeItems: 'center',
                flex: '0 0 auto',
              }}>
                <Icon size={13} strokeWidth={2.4} />
              </div>
            );
          })()}
          <div style={{
            fontSize: '9px',
            color: C.textSec,
            flex: '2 1 260px',
            minWidth: '220px',
            lineHeight: 1.35,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {fallbackWorkflow.description} Prerequisite: {fallbackWorkflow.prerequisite}.
          </div>
          <span style={{
            fontSize: '9px',
            color: canRunSelectedWorkflow ? C.green : C.orange,
            fontWeight: '700',
            background: canRunSelectedWorkflow ? '#E8F5E9' : '#FFF8E1',
            border: `1px solid ${canRunSelectedWorkflow ? '#B7E2BF' : '#FFE082'}`,
            borderRadius: '4px',
            padding: '4px 8px',
            whiteSpace: 'nowrap',
          }}>
            {fallbackWorkflow.execution || (canRunSelectedWorkflow ? 'API connected' : 'Design queued')}
          </span>
          {selectedWorkflow === recommendedWorkflowId && (
            <span style={{
              fontSize: '9px',
              fontWeight: '700',
              color: C.primary,
              background: '#FFFFFF',
              border: `1px solid ${C.primaryLight}`,
              borderRadius: '4px',
              padding: '4px 8px',
              whiteSpace: 'nowrap',
            }}>
              Recommended
            </span>
          )}
        </div>

        <div style={{
          marginTop: '6px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px',
          alignItems: 'center',
        }}>
          <span style={{
            fontSize: '9px',
            fontWeight: '700',
            color: C.textPrimary,
            background: C.bg,
            border: `1px solid ${C.border}`,
            borderRadius: '999px',
            padding: '3px 8px',
          }}>
            {workflowOptions.length} workflows
          </span>
          <span style={{
            fontSize: '9px',
            color: C.textSec,
          }}>
            {groupedWorkflows.map(group => `${group.category} ${group.items.length}`).join(' · ')}
          </span>
        </div>
          </>
        )}

        <div style={{
          marginTop: '6px',
          display: 'grid',
          gridTemplateColumns: 'minmax(220px, 1.3fr) minmax(180px, 0.7fr)',
          gap: '6px',
        }}>
          <div style={{
            border: `1px solid ${C.border}`,
            borderRadius: '4px',
            padding: '6px',
            background: C.bg,
          }}>
            <div style={{ fontSize: '9px', fontWeight: '700', color: C.textPrimary, marginBottom: '5px' }}>
              Stages
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              {fallbackWorkflow.stages.map((stage, idx) => (
                <span
                  key={`${fallbackWorkflow.id}-${stage}`}
                  style={{
                    fontSize: '8px',
                    color: C.textPrimary,
                    background: C.surface,
                    border: `1px solid ${C.borderDark}`,
                    borderRadius: '4px',
                    padding: '3px 5px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {idx + 1}. {stage}
                </span>
              ))}
            </div>
          </div>
          <div style={{
            border: `1px solid ${C.border}`,
            borderRadius: '4px',
            padding: '6px',
            background: C.bg,
          }}>
            <div style={{ fontSize: '9px', fontWeight: '700', color: C.textPrimary, marginBottom: '5px' }}>
              Outputs
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              {fallbackWorkflow.outputs.map(output => (
                <span
                  key={`${fallbackWorkflow.id}-${output}`}
                  style={{
                    fontSize: '8px',
                    color: C.textSec,
                    background: C.surface,
                    border: `1px solid ${C.border}`,
                    borderRadius: '4px',
                    padding: '3px 5px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {output}
                </span>
              ))}
            </div>
          </div>
        </div>

        {!isImportWorkflow(selectedWorkflow) && (
          <div style={{
            marginTop: '8px',
            border: `1px solid ${C.border}`,
            borderRadius: '4px',
            padding: '8px',
            background: C.surface,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap',
          }}>
            {selectedWorkflow === 'instance.link' && (
              <>
                <label style={{ fontSize: '10px', fontWeight: '700', color: C.textPrimary }}>
                  Source instance
                </label>
                <select
                  value={workflowSourceFileId || selectedImportArtifactEntry?.fileId || ''}
                  onChange={(e) => setWorkflowSourceFileId(e.target.value)}
                  style={{
                    minWidth: '220px',
                    padding: '4px 8px',
                    fontSize: '10px',
                    border: `1px solid ${C.borderDark}`,
                    borderRadius: '3px',
                  }}
                >
                  <option value="">{importArtifactCandidates.length > 0 ? 'Select imported instance' : 'No completed import artifacts available'}</option>
                  {importArtifactCandidates.map((entry) => (
                    <option key={entry.fileId} value={entry.fileId}>
                      {entry.label}
                    </option>
                  ))}
                </select>
              </>
            )}
            <label style={{ fontSize: '10px', fontWeight: '700', color: C.textPrimary }}>
              {selectedWorkflow === 'ontology.merge' ? 'Source ontology:' : 'Ontology:'}
            </label>
            <select
              value={workflowOntologyId}
              onChange={(e) => setWorkflowOntologyId(e.target.value)}
              style={{
                minWidth: '180px',
                padding: '4px 8px',
                fontSize: '10px',
                border: `1px solid ${C.borderDark}`,
                borderRadius: '3px',
              }}
            >
              <option value="">{availableOntologies.length > 0 ? 'Select ontology' : (ontologyCatalogState.loading ? 'Loading ontology catalog...' : 'Ontology catalog unavailable')}</option>
              {availableOntologies.map(o => (
                <option key={o.optionKey || o.optionValue || o.id} value={o.optionValue || o.id}>
                  {o.name || o.id || o.optionValue}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => loadOntologyOptions({ forceLive: true })}
              disabled={ontologyCatalogState.loading}
              title={ontologyCatalogState.loading ? 'Refreshing ontology catalog...' : 'Refresh ontology catalog from live registry'}
              style={{
                padding: '4px 8px',
                background: '#fff',
                color: C.primary,
                border: `1px solid ${C.borderDark}`,
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: '700',
                cursor: ontologyCatalogState.loading ? 'not-allowed' : 'pointer',
                opacity: ontologyCatalogState.loading ? 0.6 : 1,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <RefreshCw size={12} /> Refresh
            </button>
            {selectedWorkflow === 'ontology.merge' && (
              <>
                <label style={{ fontSize: '10px', fontWeight: '700', color: C.textPrimary }}>
                  Target ontology
                </label>
                <select
                  value={workflowTargetOntologyId}
                  onChange={(e) => setWorkflowTargetOntologyId(e.target.value)}
                  style={{
                    minWidth: '180px',
                    padding: '4px 8px',
                    fontSize: '10px',
                    border: `1px solid ${C.borderDark}`,
                    borderRadius: '3px',
                  }}
                >
                  <option value="">{availableOntologies.length > 0 ? 'Select target' : (ontologyCatalogState.loading ? 'Loading ontology catalog...' : 'Ontology catalog unavailable')}</option>
                  {availableOntologies
                    .filter(o => (o.optionValue || o.id || o.prefix) !== workflowOntologyId)
                    .map(o => (
                      <option key={o.optionKey || o.optionValue || o.id} value={o.optionValue || o.id}>
                        {o.name || o.id || o.optionValue}
                      </option>
                    ))}
                </select>
              </>
            )}
            {selectedWorkflow === 'instance.link' && (
              <label style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '10px',
                color: C.textPrimary,
                fontWeight: '600',
              }}>
                <input
                  type="checkbox"
                  checked={workflowApplyLinks}
                  onChange={(e) => setWorkflowApplyLinks(e.target.checked)}
                />
                Apply approved links to Neo4j
              </label>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button
                onClick={runSelectedWorkflow}
                disabled={workflowLoading || !!workflowBlockReason}
                title={workflowBlockReason || workflowActionLabel}
                style={{
                  padding: '5px 10px',
                  background: (workflowLoading || workflowBlockReason) ? C.textMuted : C.primary,
                  color: '#fff',
                  border: 'none',
                  borderRadius: '3px',
                  fontSize: '10px',
                  fontWeight: '700',
                  cursor: (workflowLoading || workflowBlockReason) ? 'not-allowed' : 'pointer',
                }}
              >
                {workflowLoading ? 'Running...' : workflowActionLabel}
              </button>
              {selectedWorkflow === 'ontology.merge' && (
                <button
                  onClick={runNeo4jOntologyMerge}
                  disabled={workflowLoading}
                  style={{
                    padding: '5px 10px',
                    background: workflowLoading ? C.textMuted : C.accent,
                    color: '#fff',
                    border: 'none',
                    borderRadius: '3px',
                    fontSize: '10px',
                    fontWeight: '700',
                    cursor: workflowLoading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {workflowLoading ? 'Running...' : 'Merge into Neo4j'}
                </button>
              )}
            </div>
            {workflowRun?.artifact_manifest && (
              <div style={{ flexBasis: '100%', fontSize: '10px', color: C.textSec, lineHeight: 1.45 }}>
                <div>
                  Generated {workflowRun.artifact_manifest.artifacts?.length || 0} retained artifact(s) in task {workflowRun.task_id}.
                </div>
                {workflowRun?.result?.summary && (
                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '6px',
                    marginTop: '6px',
                  }}>
                    {Object.entries(workflowRun.result.summary).map(([key, value]) => (
                      <span
                        key={key}
                        style={{
                          background: C.primaryLight,
                          color: C.primaryDark,
                          border: `1px solid ${C.border}`,
                          borderRadius: '999px',
                          padding: '2px 8px',
                          fontSize: '9px',
                          fontWeight: '700',
                        }}
                      >
                        {key.replace(/_/g, ' ')}: {String(value)}
                      </span>
                    ))}
                  </div>
                )}
                {selectedWorkflow === 'instance.link' && workflowRun?.result?.summary && (
                  <div style={{ marginTop: '6px', color: C.textPrimary }}>
                    {workflowApplyLinks
                      ? 'Only high-confidence, non-ambiguous semantic links are written to Neo4j.'
                      : 'Dry-run mode: review entity, attribute, relationship, and metadata mappings before applying links to Neo4j.'}
                  </div>
                )}
                {selectedWorkflow === 'ontology.merge' && (
                  <div style={{ marginTop: '6px', color: C.textPrimary, lineHeight: 1.45 }}>
                    Use <strong>Review merge plan</strong> to inspect ontology gaps, overlaps, and conflicts first.
                    Use <strong>Merge into Neo4j</strong> when you want to commit the selected source ontology into the chosen target ontology.
                  </div>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginTop: '4px' }}>
                  {(workflowRun.artifact_manifest.artifacts || []).slice(0, 6).map(artifact => (
                    <a
                      key={artifact.path}
                      href={API_METHODS.workflow.artifactUrl(workflowRun.task_id, artifact.path)}
                      target="_blank"
                      rel="noreferrer"
                      title={artifact.absolute_path || artifact.path}
                      style={{
                        background: C.bg,
                        border: `1px solid ${C.border}`,
                        borderRadius: '3px',
                        color: C.textPrimary,
                        padding: '2px 5px',
                        fontSize: '9px',
                        maxWidth: '240px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        textDecoration: 'none',
                      }}
                    >
                      {artifact.path}
                    </a>
                  ))}
                </div>
              </div>
            )}
            {selectedWorkflow === 'ontology.merge' && workflowRun?.result && !workflowRun?.artifact_manifest && (
              <div style={{ flexBasis: '100%', fontSize: '10px', color: C.textSec, lineHeight: 1.45 }}>
                <div style={{ color: C.textPrimary }}>
                  {workflowRun.result.message || 'Ontology merge completed.'}
                </div>
                <div style={{ marginTop: '4px' }}>
                  Candidate nodes: {workflowRun.result.candidate_nodes ?? 0} | Updated nodes: {workflowRun.result.nodes_updated ?? 0}
                </div>
                {workflowRun.result.index_audit && (
                  <div style={{ marginTop: '4px' }}>
                    Index preflight: {workflowRun.result.index_audit.ensured ? 'ensured' : 'skipped'}
                    {workflowRun.result.index_audit.warning ? ` (${workflowRun.result.index_audit.warning})` : ''}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '8px 10px',
        marginBottom: '10px',
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
          gap: '8px',
          marginBottom: activeJobs.length > 0 ? '10px' : 0,
        }}>
          {[
            { label: 'Active jobs', value: jobSummary.active, color: C.primary },
            { label: 'Completed', value: jobSummary.completed, color: C.green },
            { label: 'Needs attention', value: jobSummary.failed, color: C.red },
            { label: 'Queued', value: jobSummary.pending, color: C.orange },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                minWidth: 0,
                border: `1px solid ${C.border}`,
                borderRadius: '4px',
                padding: '8px',
                background: C.bg,
              }}
            >
              <div style={{ fontSize: '10px', color: C.textSec, marginBottom: '4px' }}>{item.label}</div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>

        {activeJobs.length > 0 && (
          <div style={{
            display: 'grid',
            gap: '8px',
          }}>
            {activeJobs.map(({ file, status }) => {
              const batchLabel = formatBatchProgress(status.batchProgress);
              const phaseLabel = getCommitPhaseLabel(status.commitPhase) || getStageLabel(status.stage);
              const countsLabel = status.commitMetrics
                ? `${(status.commitMetrics.nodes_written || status.stats?.entities_found || 0).toLocaleString()} nodes · ${(status.commitMetrics.relationships_written || status.stats?.relationships_found || 0).toLocaleString()} rels`
                : `${(status.stats?.entities_found || 0).toLocaleString()} entities · ${(status.stats?.relationships_found || 0).toLocaleString()} rels`;
              return (
                <div
                  key={`job-${file.fileId}`}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(220px, 1.6fr) minmax(0, 1fr) minmax(0, 1fr)',
                    gap: '10px',
                    alignItems: 'center',
                    border: `1px solid ${C.border}`,
                    borderRadius: '4px',
                    padding: '8px 10px',
                    background: '#FBFCFE',
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {file.name}
                    </div>
                    <div style={{ fontSize: '10px', color: C.textSec, marginTop: '2px' }}>
                      {status.message || 'Running...'}
                    </div>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '10px', color: C.textSec }}>Commit phase</div>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary }}>
                      {phaseLabel || getStageLabel(status.stage)}
                      {batchLabel ? ` · ${batchLabel}` : ''}
                    </div>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '10px', color: C.textSec }}>Counts</div>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary }}>
                      {countsLabel}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pipeline Stages Workflow */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '8px 10px',
        marginBottom: '10px',
      }}>
        <p style={{ fontSize: '10px', fontWeight: '600', color: C.textPrimary, margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Stages
        </p>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
        }}>
          {activePipelineStages.map((stage, idx) => {
            const filesAtStage = stageFileCounts.get(stage.id) || 0;
            const isSelected = selectedStage === stage.id;

            // Calculate max current stage index
            let maxCurrentIdx = -1;
            const hasStartedFiles = Array.from(startedFiles).length > 0;
            if (hasStartedFiles) {
              const currentIndices = Array.from(startedFiles)
                .map(fId => {
                  const s = pipelineStatus[fId];
                  const currentStage = s?.stage || 'upload';
                  return activePipelineStages.findIndex(st =>
                    st.backendIds.includes(currentStage) || st.backendIds.includes(backendToFrontendStage[currentStage])
                  );
                });
              maxCurrentIdx = Math.max(...currentIndices, -1);
            }

            // Determine arrow color based on current stage
            let arrowColor = C.border; // default: upcoming
            if (idx < maxCurrentIdx) {
              arrowColor = C.green; // completed
            } else if (idx === maxCurrentIdx) {
              arrowColor = C.orange; // current
            }

            return (
              <React.Fragment key={stage.id}>
                {/* Stage item - fixed width for alignment */}
                <div
                  onClick={() => setSelectedStage(stage.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    width: '58px',
                    cursor: 'pointer',
                    textAlign: 'center',
                  }}
                >
                  {/* Stage circle */}
                  <div
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      background: (() => {
                        if (isSelected) return C.primary;
                        if (idx < maxCurrentIdx) return C.green; // completed
                        if (idx === maxCurrentIdx) return C.orange; // current
                        return C.bg; // upcoming
                      })(),
                      color: (idx <= maxCurrentIdx || isSelected) ? '#fff' : C.textPrimary,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: '700',
                      fontSize: '10px',
                      flexShrink: 0,
                      border: `2px solid ${(idx === maxCurrentIdx && !isSelected) ? C.orange : (isSelected ? C.primary : C.borderDark)}`,
                      transition: 'all 0.3s ease',
                      boxShadow: isSelected ? `0 0 0 2px ${C.primaryLight}` : (idx <= maxCurrentIdx ? `0 0 0 2px rgba(40, 167, 69, 0.2)` : 'none'),
                    }}
                  >
                    {idx + 1}
                  </div>
                  
                  {/* Stage label */}
                  <div style={{
                    fontSize: '9px',
                    fontWeight: '600',
                    color: (() => {
                      if (isSelected) return C.primary;
                      if (idx < maxCurrentIdx) return C.green; // completed
                      if (idx === maxCurrentIdx) return C.orange; // current
                      return C.textPrimary; // upcoming
                    })(),
                    marginTop: '3px',
                    lineHeight: '1.2',
                    transition: 'color 0.3s ease',
                  }}>
                    {stage.label}
                  </div>
                  {/* Stage description */}
                  <div style={{
                    fontSize: '8px',
                    color: C.textMuted,
                    marginTop: '1px',
                    lineHeight: '1.2',
                  }}>
                    {stage.description}
                  </div>
                  {/* File count badge */}
                  {filesAtStage > 0 && (
                    <div style={{
                      fontSize: '9px',
                      fontWeight: '700',
                      color: '#fff',
                      background: C.primary,
                      borderRadius: '8px',
                      padding: '1px 6px',
                      marginTop: '4px',
                    }}>
                      {filesAtStage}
                    </div>
                  )}
                </div>

                {/* Arrow connector (except last) */}
                {idx < activePipelineStages.length - 1 && (
                  <div style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '24px',
                    minWidth: '12px',
                  }}>
                    <div style={{
                      width: '100%',
                      height: '2px',
                      background: arrowColor,
                      position: 'relative',
                      transition: 'background 0.3s ease',
                    }}>
                      <div style={{
                        position: 'absolute',
                        right: '-3px',
                        top: '-3px',
                        width: 0,
                        height: 0,
                        borderLeft: `6px solid ${arrowColor}`,
                        borderTop: '4px solid transparent',
                        borderBottom: '4px solid transparent',
                        transition: 'border-left-color 0.3s ease',
                      }} />
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Selected Stage Details */}
        {selectedStage && (
          <div style={{
            marginTop: '8px',
            paddingTop: '8px',
            borderTop: `1px solid ${C.border}`,
          }}>
            {(() => {
              const stage = activePipelineStages.find(s => s.id === selectedStage);
              return (
                <div>
                  <div style={{
                    fontSize: '10px',
                    fontWeight: '600',
                    color: C.textPrimary,
                    marginBottom: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}>
                    <span>{stage?.label} - Files in this stage: {selectedStageFiles.length}</span>
                    {isImportWorkflow(selectedWorkflow) && selectedStage === activePipelineStages[0]?.id && (
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                          padding: '2px 8px',
                          background: C.primary,
                          color: '#fff',
                          border: 'none',
                          borderRadius: '2px',
                          fontSize: '9px',
                          fontWeight: '600',
                          cursor: 'pointer',
                        }}
                      >
                        + Add Files
                      </button>
                      )}
                  </div>
                  {selectedStageFiles.length > 0 ? (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {selectedStageFiles.map(f => (
                        <div key={f.fileId} style={{
                          background: '#E8F1FC',
                          border: `1px solid ${C.primary}`,
                          borderRadius: '3px',
                          padding: '2px 6px',
                          fontSize: '9px',
                          color: C.primary,
                          fontWeight: '500',
                        }}>
                          {f.name}{f.pendingMetadata ? ' (pending metadata)' : ''}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      fontSize: '11px',
                      color: C.textMuted,
                      fontStyle: 'italic',
                    }}>
                      {selectedWorkflow === 'ontology.create'
                        ? 'Upload an XSD, OWL, RDF, TTL, XMI, or EXPRESS file, then complete namespace and prefix capture to continue.'
                        : isImportWorkflow(selectedWorkflow)
                          ? 'No files in this stage yet'
                          : 'This workflow runs from the selected ontology or retained artifacts.'}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div style={{
          background: '#FFEBEE',
          border: `2px solid ${C.red}`,
          borderRadius: '6px',
          padding: '12px 16px',
          marginBottom: '20px',
          fontSize: '12px',
          color: C.red,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontWeight: '500',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1 }}>
            <AlertTriangle size={14} aria-hidden="true" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            style={{
              background: 'transparent',
              border: 'none',
              color: C.red,
              cursor: 'pointer',
              padding: '0 0 0 10px',
              fontSize: '20px',
              fontWeight: '300',
              lineHeight: '1',
            }}
            title="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {/* File upload input - hidden */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileInput}
        accept={supportedFormats.map(f => f.ext).join(',')}
        style={{ display: 'none' }}
      />

      {selectedWorkflow === 'ontology.create' && (
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '8px 10px',
        marginBottom: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap',
      }}>
        <div style={{ minWidth: 0, flex: '1 1 420px' }}>
          <div style={{ fontSize: '10px', fontWeight: '700', color: C.textPrimary }}>
            Ontology registration workflow
          </div>
          <div style={{ fontSize: '10px', color: C.textSec, lineHeight: 1.45, marginTop: '2px' }}>
            Use this flow for ontology or schema sources only. Namespace capture, preview, and registration happen here; instance ingestion stays in
            <span style={{ color: C.primary, fontWeight: '700' }}> Import instance graph</span>.
          </div>
          {ontologyCatalogState.message && (
            <div style={{
              fontSize: '9px',
              color: ontologyCatalogState.stale ? C.orange : C.textSec,
              marginTop: '4px',
            }}>
              {ontologyCatalogState.message}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => loadOntologyOptions({ forceLive: true })}
          disabled={ontologyCatalogState.loading}
          style={{
            padding: '4px 10px',
            background: '#fff',
            color: C.primary,
            border: `1px solid ${C.borderDark}`,
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: '700',
            cursor: ontologyCatalogState.loading ? 'not-allowed' : 'pointer',
            opacity: ontologyCatalogState.loading ? 0.6 : 1,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <RefreshCw size={12} /> Refresh ontology list
        </button>
        <button
          type="button"
          onClick={runSelectedWorkflow}
          disabled={!!workflowBlockReason || workflowLoading}
          style={{
            padding: '4px 12px',
            background: (workflowBlockReason || workflowLoading) ? C.textMuted : C.green,
            color: '#fff',
            border: 'none',
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: '700',
            cursor: (workflowBlockReason || workflowLoading) ? 'not-allowed' : 'pointer',
            opacity: (workflowBlockReason || workflowLoading) ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {workflowLoading ? 'Running...' : 'Register ontology'}
        </button>
      </div>
      )}

      {/* Structural import kickoff */}
      {selectedWorkflow === 'instance.import' && (
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '6px 10px',
        marginBottom: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap',
      }}>
        <div style={{ minWidth: 0, flex: '1 1 420px' }}>
          <div style={{ fontSize: '10px', fontWeight: '700', color: C.textPrimary }}>
            Structural import only
          </div>
          <div style={{ fontSize: '10px', color: C.textSec, lineHeight: 1.45, marginTop: '2px' }}>
            Files load first as source-faithful instance data. Ontology selection and semantic linking now happen in
            <span style={{ color: C.primary, fontWeight: '700' }}> Link instances to ontology</span>.
          </div>
          {ontologyCatalogState.message && (
            <div style={{
              fontSize: '9px',
              color: ontologyCatalogState.stale ? C.orange : C.textSec,
              marginTop: '4px',
            }}>
              {ontologyCatalogState.message}
            </div>
          )}
          {ontologyCatalogState.lastLoadedAt && (
            <div style={{ fontSize: '9px', color: C.textMuted, marginTop: '4px' }}>
              Ontology catalog source: {ontologyCatalogState.source === 'live' ? 'live registry' : ontologyCatalogState.source === 'cache' ? 'cached catalog' : 'unavailable'}
            </div>
          )}
        </div>
        <button
          onClick={runSelectedWorkflow}
          disabled={!!workflowBlockReason || workflowLoading}
          style={{
            marginLeft: 'auto',
            padding: '4px 12px',
            background: (workflowBlockReason || workflowLoading) ? C.textMuted : C.green,
            color: '#fff',
            border: 'none',
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: '700',
            cursor: (workflowBlockReason || workflowLoading) ? 'not-allowed' : 'pointer',
            opacity: (workflowBlockReason || workflowLoading) ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {workflowLoading ? 'Running...' : 'Start workflow'}
        </button>
      </div>
      )}

      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '6px 10px',
        marginBottom: '8px',
        fontSize: '10px',
        color: C.textSec,
        lineHeight: 1.45,
      }}>
        <strong style={{ color: C.textPrimary }}>Note:</strong>{' '}
        {getWorkflowNote({
          canRunSelectedWorkflow,
          fallbackWorkflow,
          mappingFileTypeContext,
          selectedWorkflow,
          selectedImportArtifactEntry,
        })}
        {workflowBlockReason && !workflowLoading && (
          <span style={{ color: C.orange, fontWeight: '700' }}> {' '}Action needed: {workflowBlockReason}</span>
        )}
      </div>

      {/* Data table */}
      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '6px',
          overflow: 'hidden',
        }}
      >
        {/* Table header */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '2fr 0.8fr 1.2fr 1fr 1.2fr 0.8fr 0.8fr 1fr',
          gap: '10px',
          padding: '8px 10px',
          background: C.bg,
          borderBottom: `1px solid ${C.border}`,
          fontWeight: '600',
          fontSize: '9px',
          color: C.textPrimary,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}>
          <div>File Name</div>
          <div>Size</div>
          <div>Status</div>
          <div style={{ textAlign: 'center' }}>Progress</div>
          <div>Current Stage</div>
          <div style={{ textAlign: 'center' }}>Entities</div>
          <div style={{ textAlign: 'center' }}>Rels</div>
          <div>Action</div>
        </div>

        {/* Empty state */}
        {files.length === 0 ? (
          <div style={{
            padding: '10px',
            background: C.bg,
            borderRadius: '0 0 6px 6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            fontSize: '10px',
            color: C.textMuted,
          }}>
            <span>Supported: CSV, JSON, STEP, STPX, XML, XSD, XMI, OWL, RDF, TTL, Excel</span>
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{
                padding: '5px 10px',
                background: C.primary,
                color: '#fff',
                border: 'none',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: '700',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              Browse files
            </button>
          </div>
        ) : (
          <>
            {/* Table rows */}
            {files.map(file => {
              const fileId = file.fileId;
              const status = fileStatusIndex.get(fileId) || { stage: 'upload', progress: 0 };
              const isStarted = startedFiles.has(fileId);
              const statusBadge = getStatusBadge(status.stage, status.progress, status.error, status.backendStage, status.committing, status.commitError, status.commitPhase);

              return (
                <div
                  key={fileId}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '2fr 0.8fr 1.2fr 1fr 1.2fr 0.8fr 0.8fr 1fr',
                    gap: '10px',
                    padding: '6px 10px',
                    borderBottom: `1px solid ${C.border}`,
                    alignItems: 'center',
                    fontSize: '11px',
                    background: status.stage === 'error' ? '#FFF5F5' : 'transparent',
                  }}
                >
                  {/* File name */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ minWidth: 0 }}>
                      <div title={file.name} style={{
                        fontWeight: '500',
                        color: C.textPrimary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {file.name}
                      </div>
                      {(status.message || file.persisted) && (
                        <div style={{
                          fontSize: '9px',
                          color: C.textSec,
                          marginTop: '2px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {file.persisted && !file.fileObj ? 'Persisted job monitor' : status.message}
                        </div>
                      )}
                    </div>
                    {file.ontologyName && (
                      <span style={{
                        fontSize: '9px',
                        fontWeight: '700',
                        padding: '2px 6px',
                        backgroundColor: C.primaryLight,
                        color: C.primary,
                        borderRadius: '3px',
                        whiteSpace: 'nowrap',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '3px'
                      }}>
                        <Network size={9} strokeWidth={2.4} aria-hidden="true" /> {file.prefix}
                      </span>
                    )}
                  </div>
                  {file.sourceNamespace && (
                    <div style={{
                      gridColumn: '1 / -1',
                      marginTop: '-2px',
                      fontSize: '9px',
                      color: C.textSec,
                      fontFamily: 'monospace',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }} title={file.sourceNamespace}>
                      Namespace: {file.sourceNamespace}
                    </div>
                  )}

                  {/* File size */}
                  <div style={{
                    color: C.textMuted,
                    fontSize: '11px',
                  }}>
                    {formatFileSize(file.size)}
                  </div>

                  {/* Status badge */}
                  <div style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '4px 8px',
                    background: statusBadge.bg,
                    color: statusBadge.color,
                    borderRadius: '4px',
                    fontWeight: '600',
                    fontSize: '10px',
                    whiteSpace: 'nowrap',
                  }}>
                    {statusBadge.text}
                  </div>

                  {/* Progress bar */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}>
                    <div style={{
                      flex: 1,
                      height: '6px',
                      background: C.bg,
                      borderRadius: '3px',
                      overflow: 'hidden',
                      minWidth: '50px',
                    }}>
                      <div style={{
                        width: `${status.progress}%`,
                        height: '100%',
                        background: status.stage === 'error' ? C.red : C.green,
                        transition: 'width 0.3s ease',
                      }} />
                    </div>
                    <div style={{
                      minWidth: '28px',
                      textAlign: 'right',
                      color: C.textSec,
                      fontSize: '10px',
                      fontWeight: '600',
                    }}>
                      {Math.round(status.progress)}%
                    </div>
                  </div>

                  {/* Current stage */}
                  <div style={{
                    color: C.textSec,
                    fontWeight: '500',
                    fontSize: '11px',
                  }}
                  title={status.stats?.ontology_mapping ? `Import context: ${status.stats.ontology_mapping === 'auto' ? 'Auto-detected from ' + (status.stats.mapping_type || 'file format') : status.stats.ontology_mapping}` : 'Structural import'}>
                      <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {getStageLabel(status.stage)}
                        {status.stage === 'map' && status.stats?.ontology_mapping && (
                          <span style={{ fontSize: '9px', color: C.orange, marginLeft: '4px' }}>
                            ({status.stats.ontology_mapping === 'auto' ? 'Auto' : status.stats.ontology_mapping})
                          </span>
                        )}
                        {typeof status.shaclConforms !== 'undefined' && status.shaclConforms !== null && (
                          <span style={{ fontSize: '10px', fontWeight: '700', marginLeft: '8px', color: status.shaclConforms ? C.green : C.orange }}>
                            {status.shaclConforms ? 'SHACL OK' : 'SHACL Failed'}
                          </span>
                        )}
                      </div>
                      {(status.commitPhase || status.batchProgress) && (
                        <div style={{ fontSize: '9px', color: C.textSec, marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {[getCommitPhaseLabel(status.commitPhase), formatBatchProgress(status.batchProgress)].filter(Boolean).join(' · ')}
                        </div>
                      )}
                  </div>

                  {/* Entities count */}
                  <div style={{
                    color: status.stats?.entities_found ? C.textPrimary : C.textMuted,
                    textAlign: 'center',
                    fontWeight: '600',
                    fontSize: '11px',
                  }}>
                    {status.stats?.entities_found !== undefined ? status.stats.entities_found : '-'}
                  </div>

                  {/* Relationships count */}
                  <div style={{
                    color: status.stats?.relationships_found ? C.textPrimary : C.textMuted,
                    textAlign: 'center',
                    fontWeight: '600',
                    fontSize: '11px',
                  }}>
                    {status.stats?.relationships_found !== undefined ? status.stats.relationships_found : '-'}
                  </div>

                  {/* Action buttons */}
                  <div style={{
                    display: 'flex',
                    gap: '6px',
                    justifyContent: 'flex-end',
                  }}>
                    {!isStarted && (status.stage === 'upload' || status.error) && (
                      <button
                        onClick={() => {
                          if (file.workflowId === 'document.unstructured') {
                            startDocumentPipeline(file);
                            return;
                          }
                          if (file.workflowId === 'ontology.create') {
                            if (file.pendingMetadata) {
                              setMetadataFormPrefill({
                                ontologyName: file.ontologyName || '',
                                prefix: file.prefix || '',
                                description: file.description || '',
                                generationType: file.generationType || '',
                                schemaType: file.schemaType || 'schema',
                              });
                              setPendingFileForMetadata(file.fileObj);
                              setPendingMetadataFileId(file.fileId);
                              setShowMetadataForm(true);
                              return;
                            }
                            startOntologyRegistration(file);
                            return;
                          }
                          startImport(file);
                        }}
                        disabled={!canRunSelectedWorkflow || (!file.fileObj && file.persisted)}
                        style={{
                          padding: '6px 10px',
                          background: (canRunSelectedWorkflow && (file.fileObj || !file.persisted)) ? C.primary : C.textMuted,
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: '600',
                          cursor: (canRunSelectedWorkflow && (file.fileObj || !file.persisted)) ? 'pointer' : 'not-allowed',
                          opacity: (canRunSelectedWorkflow && (file.fileObj || !file.persisted)) ? 1 : 0.6,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        title={
                          !file.fileObj && file.persisted
                            ? 'This restored entry can be monitored, but it cannot be restarted without re-attaching the source file.'
                            : file.workflowId === 'ontology.create' && file.pendingMetadata
                              ? 'Add ontology details before registration'
                            : canRunSelectedWorkflow
                              ? 'Start workflow for this file'
                              : 'Selected workflow is not connected to backend services yet'
                        }
                      >
                        <Play size={12} /> {file.workflowId === 'ontology.create' && file.pendingMetadata ? 'Details' : (status.error ? 'Retry' : 'Start')}
                      </button>
                    )}
                    {isStarted && isProcessingJob(status) && (
                      <button
                        style={{
                          padding: '6px 10px',
                          background: C.orange,
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: '600',
                          cursor: 'not-allowed',
                          opacity: 0.7,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        disabled
                      >
                        <RefreshCw size={12} /> Processing
                      </button>
                    )}
                    {(isStarted || !!status.taskId)
                      && (isReadyToLoad(status) || status.commitPhase === 'error' || status.commitError)
                      && !status.error
                      && !status.committed
                      && !isCommitInFlight(status)
                      && (
                      <button
                        onClick={() => {
                          setConfirmingImport(status.taskId);
                          // Run pre-commit check immediately when modal opens
                          setPreCheck({ loading: true });
                          apiClient.get(buildUrl(replaceParams(API.import.preCommit, { task_id: status.taskId })), { timeout: 300000 })
                            .then(r => {
                              const payload = r.data || {};
                              setPreCheck({ loading: false, ...payload });
                            })
                            .catch((err) => setPreCheck({
                              loading: false,
                              ready: false,
                              checks: { neo4j: { ok: false }, task: { ok: false } },
                              reason: err?.message || 'Pre-commit check failed.',
                            }));
                        }}
                        style={{
                          padding: '6px 10px',
                          background: C.green,
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: '600',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        title={status.commitError || status.commitPhase === 'error' ? 'Retry commit to Neo4j' : 'Load to Neo4j'}
                      >
                        {status.commitError || status.commitPhase === 'error' ? <RotateCcw size={12} /> : <Upload size={12} />}
                        {status.commitError || status.commitPhase === 'error' ? 'Retry commit' : 'Load to Neo4j'}
                      </button>
                    )}
                    {isCommitInFlight(status) && (
                      <button
                        disabled
                        style={{
                          padding: '6px 10px',
                          background: '#F57F17',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: '600',
                          cursor: 'not-allowed',
                          opacity: 0.75,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <Loader2 size={12} /> {getCommitPhaseLabel(status.commitPhase) ? `${getCommitPhaseLabel(status.commitPhase)}...` : 'Loading to Neo4j...'}
                      </button>
                    )}
                    {status.taskId && (status.status === 'completed' || status.progress === 100) && !status.error && (
                      <select
                        defaultValue=""
                        onChange={(event) => {
                          const format = event.target.value;
                          event.target.value = '';
                          if (format) downloadOntologyExport(status.taskId, format);
                        }}
                        title="Export generated ontology"
                        style={{
                          padding: '6px 8px',
                          border: `1px solid ${C.border}`,
                          borderRadius: '4px',
                          background: C.bg,
                          color: C.textPrimary,
                          fontSize: '10px',
                          fontWeight: 700,
                          maxWidth: '118px',
                        }}
                      >
                        <option value="">Export</option>
                        <option value="ttl">TTL</option>
                        <option value="rdf">RDF/XML</option>
                        <option value="owl">OWL/XML</option>
                        <option value="jsonld">JSON-LD</option>
                      </select>
                    )}
                    {status.progress === 100 && !status.error && status.committed && (
                      <div style={{
                        padding: '6px 10px',
                        background: '#E8F5E9',
                        color: C.green,
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontWeight: '600',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}>
                        <Check size={12} /> Committed
                      </div>
                    )}
                    <button
                      onClick={() => removeFile(fileId)}
                      style={{
                        padding: '6px 8px',
                        background: 'transparent',
                        color: C.red,
                        border: `1px solid ${C.red}`,
                        borderRadius: '4px',
                        fontSize: '10px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '2px',
                      }}
                      title="Remove file"
                    >
                      <X size={12} />
                    </button>
                  </div>
                </div>
              );
            })}

            {/* Bulk actions footer */}
            {files.length > 0 && (
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 10px',
                background: C.bg,
                borderTop: `1px solid ${C.border}`,
                fontSize: '10px',
              }}>
                {(() => {
                <div style={{ color: C.textMuted }}>
                  {files.length} file{files.length !== 1 ? 's' : ''} • {activeProcessingCount} processing
                </div>
                })()}
                <button
                  onClick={startAllImports}
                  disabled={pendingFileCount === 0 || !canRunSelectedWorkflow}
                  style={{
                    padding: '4px 10px',
                    background: (pendingFileCount === 0 || !canRunSelectedWorkflow) ? C.textMuted : C.green,
                    color: '#fff',
                    border: 'none',
                    borderRadius: '3px',
                    fontSize: '10px',
                    fontWeight: '600',
                    cursor: (pendingFileCount === 0 || !canRunSelectedWorkflow) ? 'not-allowed' : 'pointer',
                    opacity: (pendingFileCount === 0 || !canRunSelectedWorkflow) ? 0.5 : 1,
                  }}>
                  Run all
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Preview Modal */}
      {confirmingImport && previewData && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: C.surface,
            borderRadius: '8px',
            padding: '24px',
            maxWidth: '800px',
            maxHeight: '80vh',
            overflow: 'auto',
            boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '700', color: C.textPrimary }}>
                Preview
              </h3>
              <button
                onClick={() => setConfirmingImport(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: C.textMuted,
                }}
              >
                ×
              </button>
            </div>

            {/* Preview stats */}
            <div style={{
              background: C.bg,
              border: `1px solid ${C.border}`,
              borderRadius: '4px',
              padding: '12px',
              marginBottom: '16px',
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Total Rows</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primary }}>
                    {previewData.row_count ?? 0}
                  </div>
                </div>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Columns</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primary }}>
                    {(previewData.columns || []).length}
                  </div>
                </div>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Node Labels</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primary }}>
                    {previewData.auto_schema?.nodes?.length || 1}
                  </div>
                </div>
              </div>
            </div>

            {/* Column list */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: '600', color: C.textPrimary, marginBottom: '8px' }}>
                Columns
              </div>
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '6px',
              }}>
                {(previewData.columns || []).map((col, idx) => (
                  <span
                    key={`col-${idx}-${col}`}
                    style={{
                      background: C.primaryLight,
                      color: C.primary,
                      padding: '4px 8px',
                      borderRadius: '3px',
                      fontSize: '11px',
                      fontWeight: '500',
                    }}
                  >
                    {col}
                  </span>
                ))}
              </div>
            </div>

            {/* Sample rows */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: '600', color: C.textPrimary, marginBottom: '8px' }}>
                Sample Data (First 5 Rows)
              </div>
              <div style={{
                background: C.bg,
                border: `1px solid ${C.border}`,
                borderRadius: '4px',
                overflow: 'auto',
                maxHeight: '200px',
              }}>
                <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}`, background: C.bg }}>
                      {(previewData.columns || []).slice(0, 5).map((col, colIdx) => (
                        <th
                          key={`header-${colIdx}-${col}`}
                          style={{
                            padding: '8px',
                            textAlign: 'left',
                            fontWeight: '600',
                            color: C.textPrimary,
                            borderRight: colIdx < 4 ? `1px solid ${C.border}` : 'none',
                          }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(previewData.sample_rows || []).map((row, rowIdx) => (
                      <tr key={`row-${rowIdx}`} style={{ borderBottom: `1px solid ${C.border}` }}>
                        {(previewData.columns || []).slice(0, 5).map((col, colIdx) => (
                          <td
                            key={`cell-${rowIdx}-${col}`}
                            style={{
                              padding: '8px',
                              borderRight: colIdx < 4 ? `1px solid ${C.border}` : 'none',
                              color: C.textPrimary,
                            }}
                          >
                            {String(row[col] || '-').substring(0, 30)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Pre-commit checks */}
            <div style={{
              background: preCheck?.ready === false ? '#FFEBEE' : preCheck?.ready === true ? '#E8F5E9' : C.bg,
              border: `1px solid ${preCheck?.ready === false ? '#FFCDD2' : preCheck?.ready === true ? '#C8E6C9' : C.border}`,
              borderRadius: '6px',
              padding: '10px 14px',
              marginBottom: '12px',
              fontSize: '12px',
            }}>
              {preCheck?.loading && (
                <div style={{ color: C.textSec, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ display: 'inline-block', width: 12, height: 12, border: `2px solid ${C.border}`, borderTop: `2px solid ${C.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                  Checking status...
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              )}
              {!preCheck?.loading && preCheck && (
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, color: preCheck.ready ? '#067647' : '#B42318' }}>
                    {preCheck.ready ? 'Ready to commit' : 'Cannot commit'}
                  </span>
                  {preCheck.checks?.neo4j && (
                    <span style={{ color: preCheck.checks.neo4j.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.neo4j.ok ? 'OK' : 'Failed'} Neo4j: {preCheck.checks.neo4j.message || (preCheck.checks.neo4j.ok ? 'Connected' : 'Unreachable')}
                    </span>
                  )}
                  {preCheck.checks?.task && (
                    <span style={{ color: preCheck.checks.task.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.task.ok ? 'OK' : 'Failed'} Task: {preCheck.checks.task.status}
                      {preCheck.checks.task.rows ? ` · ${preCheck.checks.task.rows.toLocaleString()} rows` : ''}
                    </span>
                  )}
                  {!preCheck.ready && preCheck.reason && (
                    <span style={{ color: '#B42318', fontStyle: 'italic' }}>{preCheck.reason}</span>
                  )}
                </div>
              )}
              {!preCheck && (
                <span style={{ color: C.textMuted }}>Checks run before load.</span>
              )}
            </div>

            {/* Actions */}
            <div style={{
              display: 'flex',
              gap: '8px',
              justifyContent: 'flex-end',
            }}>
              <button
                onClick={() => setConfirmingImport(null)}
                style={{
                  padding: '8px 16px',
                  background: C.border,
                  color: C.textPrimary,
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => commitImport(confirmingImport)}
                disabled={preCheck?.loading || preCheck?.ready === false}
                style={{
                  padding: '8px 16px',
                  background: (preCheck?.loading || preCheck?.ready === false) ? C.textMuted : C.green,
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: (preCheck?.loading || preCheck?.ready === false) ? 'not-allowed' : 'pointer',
                }}
              >
                {preCheck?.loading ? 'Checking...' : 'Load to Neo4j'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
