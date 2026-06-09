import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  X,
  Play,
  RefreshCw,
  AlertTriangle,
  Network,
  Check,
  Upload,
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

export default function DataImportPipeline() {
  const [files, setFiles] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState({});
  const [error, setError] = useState(null);
  const [startedFiles, setStartedFiles] = useState(new Set());
  const [selectedStage, setSelectedStage] = useState('upload');
  const [previewData, setPreviewData] = useState(null);
  // eslint-disable-next-line no-unused-vars
  const [previewTaskId, setPreviewTaskId] = useState(null);
  const [confirmingImport, setConfirmingImport] = useState(null);
  const [preCheck, setPreCheck] = useState(null); // { loading, ready, checks, reason }
  const fileInputRef = useRef(null);
  const [selectedWorkflow, setSelectedWorkflow] = useState('instance.import');
  const [workflowOptions, setWorkflowOptions] = useState(workflowCatalog);
  const [workflowOntologyId, setWorkflowOntologyId] = useState('');
  const [workflowTargetOntologyId, setWorkflowTargetOntologyId] = useState('');
  const [workflowRun, setWorkflowRun] = useState(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);

  // Ontology mapping selection
  const [availableOntologies, setAvailableOntologies] = useState([]);
  const [availableMappings, setAvailableMappings] = useState([]);
  const [requiredMappings, setRequiredMappings] = useState([]);
  const [mappingFileTypeContext, setMappingFileTypeContext] = useState('');
  const [selectedOntology, setSelectedOntology] = useState('');
  
  // Ontology metadata form for XSD/XMI files
  const [showMetadataForm, setShowMetadataForm] = useState(false);
  const [pendingFileForMetadata, setPendingFileForMetadata] = useState(null);
  const [isMetadataLoading, setIsMetadataLoading] = useState(false);
  const [metadataFormPrefill, setMetadataFormPrefill] = useState(null);

  // Get ontologies from centralized context (shared across all components)
  const { ontologies: contextOntologies } = useOntologies();

  // Transform context ontologies into DataImportPipeline format
  useEffect(() => {
    try {
      const allOntologies = contextOntologies.map(ont => ({
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
      // Deduplicate by prefix (or id when prefix empty) — keep latest uploaded_at per key
      const byKey = new Map();
      allOntologies.forEach(o => {
        const key = o.prefix || o.id;
        if (!byKey.has(key) || o.uploaded_at > (byKey.get(key).uploaded_at || '')) {
          byKey.set(key, o);
        }
      });
      const byId = new Map();
      Array.from(byKey.values()).forEach((o) => {
        const key = o.value || o.id || `${o.prefix}:${o.file}`;
        if (!byId.has(key) || o.uploaded_at > (byId.get(key).uploaded_at || '')) {
          byId.set(key, {
            ...o,
            optionKey: `${key}:${o.prefix || 'no-prefix'}:${o.file || 'no-file'}`,
            optionValue: key,
          });
        }
      });
      setAvailableOntologies(Array.from(byId.values()));
      setError(null);
    } catch (err) {
      console.error('Failed to process ontologies:', err);
      setError(`Failed to process ontologies: ${err.message}`);
      setAvailableOntologies([]);
    }
  }, [contextOntologies]);

  

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
    const pending = files.find(f => !startedFiles.has(f.fileId));
    const contextFile = pending || pendingFileForMetadata || files[0];
    const fileTypeContext = contextFile ? inferFileTypeFromExtension(contextFile.name) : '';
    setMappingFileTypeContext(fileTypeContext);

    const fetchAlignmentOptions = async () => {
      try {
        const response = await API_METHODS.ontology.getAlignmentOptions(fileTypeContext);
        const body = response.data || {};
        setAvailableMappings(body.mappings || []);
        setRequiredMappings(body.required_mappings || []);
      } catch (_err) {
        setAvailableMappings([]);
        setRequiredMappings([]);
      }
    };

    fetchAlignmentOptions();
  }, [files, startedFiles, pendingFileForMetadata]);

  useEffect(() => {
    if (!selectedOntology) return;
    const optionIds = new Set(
      (isImportWorkflow(selectedWorkflow)
        ? availableMappings.map(m => m.id)
        : availableOntologies.map(o => o.optionValue || o.id || o.prefix)
      ).filter(Boolean)
    );
    if (!optionIds.has(selectedOntology)) {
      setSelectedOntology('');
    }
  }, [selectedOntology, availableMappings, availableOntologies, selectedWorkflow]);

  useEffect(() => {
    if (selectedWorkflow !== 'ontology.merge' && workflowTargetOntologyId) {
      setWorkflowTargetOntologyId('');
      return;
    }
    if (selectedWorkflow === 'ontology.merge' && workflowTargetOntologyId && workflowTargetOntologyId === workflowOntologyId) {
      setWorkflowTargetOntologyId('');
    }
  }, [selectedWorkflow, workflowOntologyId, workflowTargetOntologyId]);

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files);
    }
  };

  const handleFiles = (fileList) => {
    const newFiles = Array.from(fileList).filter(file => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      return supportedFormats.some(f => f.ext === ext);
    });

    if (newFiles.length === 0) {
      setError('No supported files. Accepted: ' + supportedFormats.map(f => f.ext).join(', '));
      return;
    }

    // F3: client-side file size validation (500 MB cap matches backend MAX_FILE_SIZE)
    const MAX_SIZE = 500 * 1024 * 1024;
    const oversized = newFiles.filter(f => f.size > MAX_SIZE);
    if (oversized.length > 0) {
      setError(`File too large (max 500 MB): ${oversized.map(f => f.name).join(', ')}`);
      return;
    }

    // Check if this is an ontology file requiring metadata capture
    const firstFile = newFiles[0];
    const ext = '.' + firstFile.name.split('.').pop().toLowerCase();
    const recommendedWorkflow = recommendWorkflowForFile(firstFile.name);
    setSelectedWorkflow(recommendedWorkflow);
    
    if (['.xsd', '.xmi', '.mdxml', '.owl', '.rdf', '.ttl'].includes(ext)) {
      setMetadataFormPrefill(null);
      setPendingFileForMetadata(firstFile);
      setShowMetadataForm(true);
      setError(null);
      return;
    }

    // For regular files, add to list and proceed normally
    const filesWithIds = newFiles.map(file => ({
      fileId: file.name + '_' + Math.random().toString(36).substr(2, 9),
      name: file.name,
      size: file.size,
      fileObj: file,
      workflowId: recommendWorkflowForFile(file.name),
      createdAt: new Date().toLocaleTimeString()
    }));

    setFiles(prev => [...prev, ...filesWithIds]);
    setError(null);
  };

  // Handle metadata form submission for ontology files
  const handleMetadataSubmit = async (metadata) => {
    if (!pendingFileForMetadata) return;
    
    setIsMetadataLoading(true);
    
    try {
      // Upload to ontology-specific endpoint (apiClient handles FormData internally)
      const uploadData = await API_METHODS.ontology.upload(pendingFileForMetadata, metadata);
      const uploadDataBody = uploadData.data || uploadData;
      
      // Create file entry with ontology metadata
      const fileId = pendingFileForMetadata.name + '_' + Math.random().toString(36).substr(2, 9);
      const newFile = {
        fileId,
        name: pendingFileForMetadata.name,
        size: pendingFileForMetadata.size,
        fileObj: pendingFileForMetadata,
        createdAt: new Date().toLocaleTimeString(),
        taskId: uploadDataBody.task_id,
        ontologyId: uploadDataBody.ontology_id,
        ontologyName: metadata.ontologyName,
        prefix: metadata.prefix,
        generationType: metadata.generationType,
        workflowId: 'ontology.create'
      };

      setFiles(prev => [...prev, newFile]);
      // Ontology uploads are already handled by /ontology/upload, so mark as completed
      // and do not send them again through /import/upload.
      setStartedFiles(prev => new Set([...prev, fileId]));
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: {
          taskId: uploadDataBody.task_id,
          stage: 'verify',
          backendStage: 'verify',
          progress: 100,
          status: 'completed',
          committed: true,
          message: `Ontology '${metadata.ontologyName}' uploaded and registered`,
          stats: {
            entities_found: uploadDataBody.nodes_merged ?? null,
            relationships_found: null,
          },
          error: false,
          completedAt: new Date().toLocaleTimeString(),
        }
      }));
      setMetadataFormPrefill(null);
      setShowMetadataForm(false);
      setPendingFileForMetadata(null);
      setError(null);

    } catch (err) {
      setError(`Error uploading ontology: ${err.message}`);
    } finally {
      setIsMetadataLoading(false);
    }
  };


  // Map file extension to ontology id (dynamic, not hardcoded)
  const getOntologyForFile = (fileName) => {
    const fileType = inferFileTypeFromExtension(fileName);

    if (fileType === 'step') return 'step_ap242_mbd3d';
    if (fileType === 'ontology') return '';
    if (fileType === 'json' || fileType === 'xml') return '';

    if (workflowOntologyId) return workflowOntologyId;
    if (selectedOntology) return selectedOntology;

    return '';
  };

  const getAlignmentPolicy = (fileName) => {
    const fileType = inferFileTypeFromExtension(fileName);
    const isRequired = fileType === 'csv' || fileType === 'excel';
    const isStep = fileType === 'step';
    const isOptionalAuto = fileType === 'json' || fileType === 'xml';
    const isDirectOntology = fileType === 'ontology';

    return {
      fileType,
      isRequired,
      isStep,
      isOptionalAuto,
      isDirectOntology,
      forcedMapping: isStep ? 'step_ap242_mbd3d' : '',
    };
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
      let ontologyToUse = workflowOntologyId || selectedOntology || getOntologyForFile(file.name);

      if (policy.isStep) {
        ontologyToUse = policy.forcedMapping;
      }

      if (
        ontologyToUse &&
        !policy.forcedMapping &&
        !availableMappings.some(m => m.id === ontologyToUse) &&
        !availableOntologies.some(o => (o.optionValue || o.id || o.prefix) === ontologyToUse)
      ) {
        throw new Error(
          `${file.name}: Selected ontology mapping is invalid. Please pick a mapping from the Ontology Alignment dropdown.`
        );
      }

      if (policy.isRequired && !ontologyToUse) {
        throw new Error(
          `${file.name}: Ontology alignment is required for ${policy.fileType.toUpperCase()} files. ` +
          'Please choose a mapping from the Ontology Alignment dropdown.'
        );
      }

      setStartedFiles(prev => new Set([...prev, fileId]));
      setPipelineStatus(prev => ({ ...prev, [fileId]: { stage: 'upload', progress: 0, message: 'Uploading...' } }));

      // Pass both ontology_id and ontology_mapping (mapping is for backward compatibility)
      if (ontologyToUse) {
        formData.append('ontology_id', ontologyToUse);
        formData.append('ontology_mapping', ontologyToUse);
      }

      const uploadData = await apiClient.post(API.import.upload, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: getImportTimeoutMs(file.fileObj),
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
          message: ontologyToUse ? `Converting with mapping: ${ontologyToUse}` : 'Converting file...'
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

  const pollPipelineProgress = async (taskId, fileId) => {
    const maxAttempts = 60;
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
                message: 'Initializing task...'
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
            taskId,
            stage: mappedStage,
            backendStage: data.current_stage,
            progress: data.progress,
            message: data.message,
            stats: normalizedStats,
            status: data.status,
            error: data.error ? true : false,
            completedAt: data.status === 'completed' ? new Date().toLocaleTimeString() : null,
            shaclConforms,
            shaclFile,
            artifact_manifest: data.artifact_manifest,
            workflow_id: data.workflow_id,
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
          setPreviewTaskId(taskId);
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
          return;
        }

        if (attempts < maxAttempts) {
          attempts++;
          setTimeout(poll, 2000);  // Poll every 2 seconds
        }
      } catch (err) {
        setPipelineStatus(prev => ({
          ...prev,
          [fileId]: { ...prev[fileId], stage: 'error', message: err.message, error: true }
        }));
      }
    };

    poll();
  };

  const startAllImports = async () => {
    const workflow = workflowOptions.find(w => w.id === selectedWorkflow) || resolveWorkflow(selectedWorkflow);
    if (workflow?.status !== 'available') {
      setError(`${getWorkflowDisplayName(selectedWorkflow)} is not connected to backend services yet. Use Import instance graph or Create ontology for current execution.`);
      return;
    }

    const filesToImport = files.filter(f => {
      if (startedFiles.has(f.fileId)) return false;
      const policy = getAlignmentPolicy(f.name);
      // Direct ontology files are handled by metadata upload flow, not import pipeline.
      if (policy.isDirectOntology) return false;
      return true;
    });
    if (filesToImport.length === 0) {
      setError('All files have already been started');
      return;
    }

    // Friendly preflight: clearly explain required alignment before starting.
    const missingRequired = filesToImport.filter(f => {
      const policy = getAlignmentPolicy(f.name);
      return policy.isRequired && !selectedOntology;
    });
    if (missingRequired.length > 0) {
      const names = missingRequired.map(f => f.name).join(', ');
      setError(`Ontology alignment is required for CSV/Excel files. Please select an ontology mapping first. Affected: ${names}`);
      return;
    }

    for (const file of filesToImport) {
      startImport(file);
    }
  };

  const runSelectedWorkflow = async () => {
    if (isImportWorkflow(selectedWorkflow)) {
      startAllImports();
      return;
    }
    if (!workflowOntologyId) {
      setError('Select an ontology catalog entry before running this workflow.');
      return;
    }
    if (selectedWorkflow === 'ontology.merge' && !workflowTargetOntologyId) {
      setError('Select a target ontology before running merge.');
      return;
    }
    if (selectedWorkflow === 'ontology.merge' && workflowTargetOntologyId === workflowOntologyId) {
      setError('Choose two different ontologies for merge.');
      return;
    }

    const latestArtifactManifest = Object.values(pipelineStatus)
      .map(s => s?.artifact_manifest)
      .filter(Boolean)
      .slice(-1)[0];
    if (selectedWorkflow === 'instance.link' && !latestArtifactManifest) {
      setError('Import an instance file first so the link workflow has retained source artifacts to analyze.');
      return;
    }
    const payload = {
      ontology_id: workflowOntologyId,
      source_ontology_id: workflowOntologyId,
      import_artifact_manifest: latestArtifactManifest,
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

  const commitImport = async (taskId) => {
    // ── Pre-commit check ────────────────────────────────────────────────────
    // Show a quick checking state in the modal before closing it
    try {
      const checkRes = await apiClient.get(
        buildUrl(replaceParams(API.import.preCommit, { task_id: taskId })),
        { timeout: 15000 }
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
      // If the pre-check itself fails (network error) warn but allow proceeding
      console.warn('[pre-commit] check failed:', checkErr.message);
    }

    // Close the review modal immediately — don't make the user wait 2-3 min
    setConfirmingImport(null);

    // Mark as "loading to Neo4j" in the file card right away
    setPipelineStatus(prev => {
      const updated = { ...prev };
      for (const [fid, status] of Object.entries(updated)) {
        if (status.taskId === taskId) {
          updated[fid] = { ...status, committing: true, progress: 80 };
        }
      }
      return updated;
    });

    // Run the actual commit in background — UI stays responsive
    const commitUrl = buildUrl(replaceParams(API.import.commit, { task_id: taskId }));
    const commitTimeoutMs = Math.max(getImportTimeoutMs({ size: 0 }), 10 * 60 * 1000);
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
                  message: commitData.message || 'Neo4j commit queued in background...',
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
                completedAt: new Date().toLocaleTimeString(),
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
              updated[fid] = { ...status, committing: false, commitError: err.message };
            }
          }
          return updated;
        });
        setError(`Commit failed: ${err.message}`);
      });
  };

  const removeFile = (fileId) => {
    const fileStatus = pipelineStatus[fileId];
    
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

  const getStatusBadge = (stage, progress, error, backendStage, committing, commitError) => {
    if (committing) {
      return { text: 'Loading to Neo4j...', bg: '#FFF8E1', color: '#F57F17' };
    }
    if (commitError) {
      return { text: 'Commit Failed', bg: '#FFEBEE', color: C.red };
    }
    if (error) {
      return { text: 'Error', bg: '#FFEBEE', color: C.red };
    }
    // 'preview' backend stage = pipeline parsed OK, waiting for user to commit to Neo4j
    if (backendStage === 'preview' || ((stage === 'verify' || stage === 'load') && progress >= 75 && progress < 100)) {
      return { text: 'Ready to Load', bg: '#E8F5E9', color: C.green };
    }
    if (progress === 100) {
      return { text: 'Complete', bg: '#E8F5E9', color: C.green };
    }
    if (progress > 0) {
      return { text: 'In Progress', bg: '#E3F2FD', color: C.primary };
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

  const getImportTimeoutMs = (file) => {
    const size = file?.size || 0;
    if (size <= 25 * 1024 * 1024) return 5 * 60 * 1000;
    if (size <= 100 * 1024 * 1024) return 8 * 60 * 1000;
    if (size <= 250 * 1024 * 1024) return 12 * 60 * 1000;
    if (size <= 400 * 1024 * 1024) return 16 * 60 * 1000;
    return 20 * 60 * 1000;
  };

  const activeWorkflow = useMemo(
    () => workflowOptions.find(w => w.id === selectedWorkflow) || workflowOptions[0] || resolveWorkflow(selectedWorkflow),
    [workflowOptions, selectedWorkflow]
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
  const contextFile = files.find(f => !startedFiles.has(f.fileId)) || files[0] || pendingFileForMetadata;
  const recommendedWorkflowId = contextFile ? recommendWorkflowForFile(contextFile.name) : selectedWorkflow;
  const canRunSelectedWorkflow = fallbackWorkflow.status === 'available';
  const pendingFileCount = files.filter(f => !startedFiles.has(f.fileId)).length;
  const activePipelineStageIds = useMemo(
    () => activePipelineStages.map(stage => stage.id).join('|'),
    [activePipelineStages]
  );

  useEffect(() => {
    if (!activePipelineStages.some(stage => stage.id === selectedStage)) {
      setSelectedStage(activePipelineStages[0]?.id || 'upload');
    }
  }, [activePipelineStageIds, activePipelineStages, selectedStage]);

  return (
    <div style={{ background: C.bg, minHeight: '100%', padding: '10px', boxSizing: 'border-box' }}>
      {/* Ontology Metadata Form Modal */}
      {showMetadataForm && (
        <OntologyMetadataForm
          selectedFile={pendingFileForMetadata}
          onSubmit={handleMetadataSubmit}
          onCancel={() => {
            setMetadataFormPrefill(null);
            setShowMetadataForm(false);
            setPendingFileForMetadata(null);
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
        padding: '8px 10px',
        marginBottom: '8px',
      }}>
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
            Workflow
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
              fontSize: '10px',
              border: `1px solid ${C.borderDark}`,
              borderRadius: '4px',
              background: C.bg,
              color: C.textPrimary,
            }}
          >
            {workflowOptions.map(option => (
              <option key={option.id} value={option.id}>
                {option.title}{option.id === recommendedWorkflowId ? ' - recommended' : ''}
              </option>
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
              Execution plan · {fallbackWorkflow.inputs}
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
              <option value="">Select ontology</option>
              {availableOntologies.map(o => (
                <option key={o.optionKey || o.optionValue || o.id} value={o.optionValue || o.id}>
                  {o.name || o.id || o.optionValue}
                </option>
              ))}
            </select>
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
                  <option value="">Select target</option>
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
            <button
              onClick={runSelectedWorkflow}
              disabled={workflowLoading}
              style={{
                marginLeft: 'auto',
                padding: '5px 10px',
                background: workflowLoading ? C.textMuted : C.primary,
                color: '#fff',
                border: 'none',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: '700',
                cursor: workflowLoading ? 'not-allowed' : 'pointer',
              }}
            >
              {workflowLoading ? 'Running...' : 'Run workflow'}
            </button>
            {workflowRun?.artifact_manifest && (
              <div style={{ flexBasis: '100%', fontSize: '10px', color: C.textSec, lineHeight: 1.45 }}>
                <div>
                  Generated {workflowRun.artifact_manifest.artifacts?.length || 0} retained artifact(s) in task {workflowRun.task_id}.
                </div>
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
          Pipeline Workflow
        </p>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
        }}>
          {activePipelineStages.map((stage, idx) => {
            const filesAtStage = files.filter(f => {
              const status = pipelineStatus[f.fileId];
              const currentStage = status?.stage || 'upload';
              return stage.backendIds.includes(currentStage) || stage.backendIds.includes(backendToFrontendStage[currentStage]);
            }).length;
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
              const stageFiles = files.filter(f => {
                const status = pipelineStatus[f.fileId];
                const currentStage = status?.stage || 'upload';
                return stage?.backendIds.includes(currentStage) || stage?.backendIds.includes(backendToFrontendStage[currentStage]);
              });
              
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
                    <span>{stage?.label} - Files in this stage: {stageFiles.length}</span>
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
                  {stageFiles.length > 0 ? (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {stageFiles.map(f => (
                        <div key={f.fileId} style={{
                          background: '#E8F1FC',
                          border: `1px solid ${C.primary}`,
                          borderRadius: '3px',
                          padding: '2px 6px',
                          fontSize: '9px',
                          color: C.primary,
                          fontWeight: '500',
                        }}>
                          {f.name}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      fontSize: '11px',
                      color: C.textMuted,
                      fontStyle: 'italic',
                    }}>
                      {isImportWorkflow(selectedWorkflow) ? 'No files in this stage yet' : 'This workflow runs from the selected ontology or retained artifacts.'}
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

      {/* Ontology Alignment & Start Pipeline */}
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
        <label style={{
          fontSize: '10px',
          fontWeight: '600',
          color: C.textPrimary,
          whiteSpace: 'nowrap',
        }}>
          Target ontology:
        </label>
        <select
          value={workflowOntologyId}
          onChange={(e) => setWorkflowOntologyId(e.target.value)}
          disabled={!canRunSelectedWorkflow}
          style={{
            flex: '1 1 260px',
            padding: '4px 8px',
            fontSize: '10px',
            border: `1px solid ${C.borderDark}`,
            borderRadius: '3px',
            background: !canRunSelectedWorkflow ? '#F1F3F5' : C.bg,
            color: C.textPrimary,
            cursor: !canRunSelectedWorkflow ? 'not-allowed' : 'pointer',
            maxWidth: '420px',
          }}
          title="Choose the ontology this import should link to."
        >
          <option key="no-target" value="">Select ontology</option>
          {availableOntologies.map(o => (
            <option key={o.optionKey || o.optionValue || o.id} value={o.optionValue || o.id}>
              {o.name || o.id || o.optionValue}{o.prefix ? ` [${o.prefix}]` : ''}
            </option>
          ))}
        </select>
        <label style={{
          fontSize: '10px',
          fontWeight: '600',
          color: C.textPrimary,
          whiteSpace: 'nowrap',
          marginLeft: '8px',
        }}>
          Ontology mapping:
        </label>
        <select
          value={selectedOntology}
          onChange={(e) => setSelectedOntology(e.target.value)}
          disabled={!canRunSelectedWorkflow}
          style={{
            flex: '1 1 260px',
            padding: '4px 8px',
            fontSize: '10px',
            border: `1px solid ${C.borderDark}`,
            borderRadius: '3px',
            background: !canRunSelectedWorkflow ? '#F1F3F5' : C.bg,
            color: C.textPrimary,
            cursor: !canRunSelectedWorkflow ? 'not-allowed' : 'pointer',
            maxWidth: '420px',
        }}
          title="Choose a mapping for CSV/Excel, or keep automatic rules for STEP/JSON/XML."
        >
          <option key="auto" value="">Automatic mapping rules</option>
          {availableMappings.map((m, idx) => {
            const label = m.name || m.id;
            return (
              <option key={m.id || `map-${idx}`} value={m.id}>
                {label}
              </option>
            );
          })}
          {availableMappings.length === 0 && (
            <option key="no-maps" value="" disabled>
              No mappings available for this file type
            </option>
          )}
        </select>
        {selectedOntology && (
          <span style={{ fontSize: '9px', color: C.textMuted }}>
            {selectedOntology}
          </span>
        )}
        <button
          onClick={runSelectedWorkflow}
          disabled={pendingFileCount === 0 || !canRunSelectedWorkflow || workflowLoading}
          style={{
            marginLeft: 'auto',
            padding: '4px 12px',
            background: (pendingFileCount === 0 || !canRunSelectedWorkflow || workflowLoading) ? C.textMuted : C.green,
            color: '#fff',
            border: 'none',
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: '700',
            cursor: (pendingFileCount === 0 || !canRunSelectedWorkflow || workflowLoading) ? 'not-allowed' : 'pointer',
            opacity: (pendingFileCount === 0 || !canRunSelectedWorkflow || workflowLoading) ? 0.5 : 1,
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
        <strong style={{ color: C.textPrimary }}>Workflow guidance:</strong>{' '}
        {!canRunSelectedWorkflow && `${fallbackWorkflow.title} is visible for planning, but backend service wiring is still required before execution.`}
        {canRunSelectedWorkflow && selectedWorkflow === 'instance.link' && 'Upload one or more files first, then choose an ontology above to generate link candidates. This workflow writes review artifacts only.'}
        {canRunSelectedWorkflow && selectedWorkflow === 'ontology.merge' && 'Choose a source ontology and a different target ontology above to generate a merge plan. This workflow writes review artifacts only.'}
        {canRunSelectedWorkflow && (selectedWorkflow === 'ontology.validate' || selectedWorkflow === 'dictionary.generate' || selectedWorkflow === 'taxonomy.generate' || selectedWorkflow === 'graph.chunk') && 'Choose an ontology above to generate the review artifact for this workflow. It does not write to Neo4j directly.'}
        {canRunSelectedWorkflow && selectedWorkflow === 'ontology.create' && mappingFileTypeContext !== 'express' && 'Schema and ontology files are registered through metadata capture. EXPRESS/XSD-style schemas create ontology structure; they do not create STEP instance graphs.'}
        {canRunSelectedWorkflow && mappingFileTypeContext === 'express' && 'EXPRESS files create ontology/schema structure from ISO 10303 definitions. Use STEP/STP/STPX when you need product instance data.'}
        {canRunSelectedWorkflow && mappingFileTypeContext === 'step' && 'STEP/STP/STPX files create an instance graph. AP242-MBD3D alignment is applied automatically when available.'}
        {selectedWorkflow === 'instance.import' && 'Pick a target ontology first, then choose a mapping if the file type needs one.'}
        {selectedWorkflow === 'instance.import' && (mappingFileTypeContext === 'csv' || mappingFileTypeContext === 'excel') && 'CSV/Excel require a mapping and a target ontology before start.'}
        {selectedWorkflow === 'instance.import' && (mappingFileTypeContext === 'json' || mappingFileTypeContext === 'xml') && 'JSON/XML can auto-generate OWL/TTL if no mapping is selected, but the target ontology still needs to be chosen.'}
        {selectedWorkflow === 'instance.import' && mappingFileTypeContext === 'ontology' && 'OWL/RDF/TTL are imported directly as ontology content (as-is).'}
        {selectedWorkflow === 'instance.import' && !mappingFileTypeContext && 'Select files to see file-type specific alignment guidance.'}
        {requiredMappings.length > 0 && (
          <span> Required mapping for current file type: {requiredMappings.join(', ')}.</span>
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
              const status = pipelineStatus[fileId] || { stage: 'upload', progress: 0 };
              const isStarted = startedFiles.has(fileId);
              const statusBadge = getStatusBadge(status.stage, status.progress, status.error, status.backendStage, status.committing, status.commitError);

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
                    <div title={file.name} style={{
                      fontWeight: '500',
                      color: C.textPrimary,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {file.name}
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
                    whiteSpace: 'nowrap',
                  }}
                  title={status.stats?.ontology_mapping ? `Ontology: ${status.stats.ontology_mapping === 'auto' ? 'Auto-detected from ' + (status.stats.mapping_type || 'file format') : status.stats.ontology_mapping}` : 'No ontology selected'}>
                      {getStageLabel(status.stage)}
                      {status.stage === 'map' && status.stats?.ontology_mapping && (
                        <span style={{ fontSize: '9px', color: C.orange, marginLeft: '4px' }}>
                          ({status.stats.ontology_mapping === 'auto' ? 'Auto' : status.stats.ontology_mapping})
                        </span>
                      )}
                      {/* SHACL status indicator */}
                      {typeof status.shaclConforms !== 'undefined' && status.shaclConforms !== null && (
                        <span style={{ fontSize: '10px', fontWeight: '700', marginLeft: '8px', color: status.shaclConforms ? C.green : C.orange }}>
                          {status.shaclConforms ? 'SHACL OK' : 'SHACL Failed'}
                        </span>
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
                          startImport(file);
                        }}
                        disabled={!canRunSelectedWorkflow}
                        style={{
                          padding: '6px 10px',
                          background: canRunSelectedWorkflow ? C.primary : C.textMuted,
                          color: '#fff',
                          border: 'none',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: '600',
                          cursor: canRunSelectedWorkflow ? 'pointer' : 'not-allowed',
                          opacity: canRunSelectedWorkflow ? 1 : 0.6,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                        title={canRunSelectedWorkflow ? 'Start workflow for this file' : 'Selected workflow is not connected to backend services yet'}
                      >
                        <Play size={12} /> {status.error ? 'Retry' : 'Start'}
                      </button>
                    )}
                    {isStarted && !status.error && !status.commitError && status.stage !== 'verify' && status.status !== 'completed' && status.progress < 75 && (
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
                    {(isStarted || !!status.taskId) && (status.stage === 'verify' || status.stage === 'load' || status.backendStage === 'preview' || status.status === 'completed') && !status.error && !status.committed && !status.committing && (
                      <button
                        onClick={() => {
                          setConfirmingImport(status.taskId);
                          setPreviewTaskId(status.taskId);
                          // Run pre-commit check immediately when modal opens
                          setPreCheck({ loading: true });
                          apiClient.get(buildUrl(replaceParams(API.import.preCommit, { task_id: status.taskId })), { timeout: 15000 })
                            .then(r => {
                              const payload = r.data || {};
                              setPreCheck({ loading: false, ...payload });
                              if (payload.ready) {
                                // Auto-advance to Neo4j load once the review state is confirmed.
                                setTimeout(() => commitImport(status.taskId), 0);
                              }
                            })
                            .catch(() => setPreCheck({ loading: false, ready: true, checks: {}, reason: null }));
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
                        title="Parsed successfully — click to load into Neo4j"
                      >
                        <Upload size={12} /> Load to Neo4j
                      </button>
                    )}
                    {status.committing && (
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
                        <Loader2 size={12} /> Loading to Neo4j...
                      </button>
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
                  const activeProcessingCount = files.filter(f => {
                    const s = pipelineStatus[f.fileId] || {};
                    if (!startedFiles.has(f.fileId)) return false;
                    if (s.error || s.commitError) return false;
                    if (s.committed || s.status === 'completed' || s.progress === 100) return false;
                    return true;
                  }).length;
                  return (
                <div style={{ color: C.textMuted }}>
                  {files.length} file{files.length !== 1 ? 's' : ''} • {activeProcessingCount} processing
                </div>
                  );
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
                  Start all
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
                Review Import Preview
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
                  Checking Neo4j connectivity and task state...
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
                <span style={{ color: C.textMuted }}>Pre-commit checks will run when you click Load to Neo4j.</span>
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
