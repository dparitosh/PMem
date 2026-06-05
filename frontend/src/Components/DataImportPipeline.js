import React, { useState, useRef, useEffect } from 'react';
import { X, Play, RefreshCw } from 'lucide-react';
import OntologyMetadataForm from './OntologyMetadataForm';
import { API_METHODS } from '../services/apiClient';
import { apiClient } from '../services/apiClient';
import { useOntologies } from '../contexts/OntologyContext';
import { API, buildUrl, replaceParams } from '../config';

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

// Pipeline stage definitions (aligned with import_master SemanticPipeline)
const PIPELINE_STAGES = [
  { id: 'upload', label: 'Upload', description: 'File validation & format detection' },
  { id: 'convert', label: 'Convert', description: 'Parse to OWL2/Turtle' },
  { id: 'map', label: 'Map', description: 'Ontology alignment' },
  { id: 'validate', label: 'Validate', description: 'SHACL & quality check' },
  { id: 'enrich', label: 'Enrich', description: 'Semantic enrichment' },
  { id: 'load', label: 'Load', description: 'Ingest to Neo4j' },
  { id: 'verify', label: 'Verify', description: 'Post-load health check' },
];

// Map backend stage names (9-stage pipeline) to frontend UI stage IDs (7-stage)
const BACKEND_TO_FRONTEND_STAGE = {
  upload:    'upload',
  detect:    'upload',
  parse:     'convert',
  validate:  'validate',
  transform: 'validate',
  preview:   'validate',
  map:       'map',
  enrich:    'enrich',
  ingest:    'load',
  load:      'load',
  verify:    'verify',
};

const SUPPORTED_FORMATS = [
  { ext: '.csv', name: 'CSV' },
  { ext: '.json', name: 'JSON' },
  { ext: '.html', name: 'HTML' },
  { ext: '.htm', name: 'HTML' },
  { ext: '.owl', name: 'OWL' },
  { ext: '.rdf', name: 'RDF' },
  { ext: '.ttl', name: 'Turtle' },
  { ext: '.plmxml', name: 'PLMXML' },
  { ext: '.3dxml', name: '3DXML (3DEXPERIENCE)' },
  { ext: '.step', name: 'STEP' },
  { ext: '.stp', name: 'STEP' },
  { ext: '.stpx', name: 'STEP XML' },
  { ext: '.xls', name: 'Excel' },
  { ext: '.xlsx', name: 'Excel' },
  { ext: '.xmi', name: 'XMI' },
  { ext: '.mdxml', name: 'MagicDraw' },
  { ext: '.xml', name: 'XML' },
  { ext: '.xsd', name: 'XSD' },
];

// Helper: determine file extension safely
const getFileExtension = (fileName) => `.${String(fileName || '').split('.').pop().toLowerCase()}`;

// Helper: infer file type from extension (stable reference)
const inferFileTypeFromExtension = (fileName) => {
  const ext = getFileExtension(fileName);
  if (['.stp', '.step', '.stpx'].includes(ext)) return 'step';
  if (['.csv'].includes(ext)) return 'csv';
  if (['.xls', '.xlsx'].includes(ext)) return 'excel';
  if (['.json'].includes(ext)) return 'json';
  if (['.3dxml'].includes(ext)) return '3dxml';
  if (['.xml'].includes(ext)) return 'xml';
  if (['.owl', '.rdf', '.ttl'].includes(ext)) return 'ontology';
  if (['.plmxml'].includes(ext)) return 'plmxml';
  if (['.xmi', '.mdxml'].includes(ext)) return 'xmi';
  if (['.xsd'].includes(ext)) return 'xsd';
  return '';
};

export default function DataImportPipeline() {
  const [files, setFiles] = useState([]);
  const [pipelineStatus, setPipelineStatus] = useState({});
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState(null);
  const [startedFiles, setStartedFiles] = useState(new Set());
  const [selectedStage, setSelectedStage] = useState('upload');
  const [previewData, setPreviewData] = useState(null);
  // eslint-disable-next-line no-unused-vars
  const [previewTaskId, setPreviewTaskId] = useState(null);
  const [confirmingImport, setConfirmingImport] = useState(null);
  const [preCheck, setPreCheck] = useState(null); // { loading, ready, checks, reason }
  const fileInputRef = useRef(null);

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
        id: ont.ontology_id || ont.id,
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
      setAvailableOntologies(Array.from(byKey.values()));
      setError(null);
    } catch (err) {
      console.error('Failed to process ontologies:', err);
      setError(`Failed to process ontologies: ${err.message}`);
      setAvailableOntologies([]);
    }
  }, [contextOntologies]);

  

  useEffect(() => {
    const pending = files.find(f => !startedFiles.has(f.fileId));
    const fileTypeContext = pending ? inferFileTypeFromExtension(pending.name) : (pendingFileForMetadata ? inferFileTypeFromExtension(pendingFileForMetadata.name) : '');
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
    const optionIds = new Set(availableMappings.map(m => m.id).filter(Boolean));
    if (!optionIds.has(selectedOntology)) {
      setSelectedOntology('');
    }
  }, [selectedOntology, availableMappings]);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === 'dragenter' || e.type === 'dragover');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files);
    }
  };

  const handleFiles = (fileList) => {
    const newFiles = Array.from(fileList).filter(file => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      return SUPPORTED_FORMATS.some(f => f.ext === ext);
    });

    if (newFiles.length === 0) {
      setError('No supported files. Accepted: ' + SUPPORTED_FORMATS.map(f => f.ext).join(', '));
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
    
    if (['.xsd', '.xmi', '.owl', '.rdf', '.ttl'].includes(ext)) {
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
        generationType: metadata.generationType
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
    const fileId = file.fileId;
    setPipelineStatus(prev => ({ ...prev, [fileId]: { stage: 'upload', progress: 0, message: 'Uploading...' } }));

    try {
      const formData = new FormData();
      formData.append('file', file.fileObj);

      const policy = getAlignmentPolicy(file.name);
      let ontologyToUse = selectedOntology || getOntologyForFile(file.name);

      if (policy.isStep) {
        ontologyToUse = policy.forcedMapping;
      }

      if (ontologyToUse && !availableMappings.some(m => m.id === ontologyToUse)) {
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

      // Pass both ontology_id and ontology_mapping (mapping is for backward compatibility)
      if (ontologyToUse) {
        formData.append('ontology_id', ontologyToUse);
        formData.append('ontology_mapping', ontologyToUse);
      }

      const uploadData = await apiClient.post(API.import.upload, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300000,  // 5 min — large files (up to 500 MB) need more than the 30s default
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

        const mappedStage = BACKEND_TO_FRONTEND_STAGE[data.current_stage] || data.current_stage || 'upload';

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
          }
        }));

        // Auto-set preview data when preview/verify stage or completed is reached
        if (data.current_stage === 'preview' || data.current_stage === 'verify' || data.status === 'completed') {
          setPreviewData(data);
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

    setStartedFiles(prev => new Set([...prev, ...filesToImport.map(f => f.fileId)]));
    
    for (const file of filesToImport) {
      startImport(file);
    }
  };

  const commitImport = async (taskId) => {
    // ── Pre-commit check ────────────────────────────────────────────────────
    // Show a quick checking state in the modal before closing it
    try {
      const checkRes = await apiClient.get(
        buildUrl(`/api/v1/import/pre-commit/${taskId}`),
        { timeout: 15000 }
      );
      const check = checkRes.data || {};
      if (!check.ready) {
        // Don't close the modal — show the blocking reason
        const reason = check.reason || 'Pre-commit check failed.';
        const neo4jOk = check.checks?.neo4j?.ok;
        const taskOk  = check.checks?.task?.ok;
        let msg = `[ERROR] Cannot commit: ${reason}`;
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
    fetch(commitUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(300000), // 5 min timeout
    })
      .then(async commitRes => {
        if (!commitRes.ok) {
          const errBody = await commitRes.json().catch(() => ({}));
          const detail = errBody?.detail || errBody?.message || errBody?.error || commitRes.statusText;
          throw new Error(detail);
        }
        const commitData = await commitRes.json().catch(() => ({}));
        const commitResult = commitData.result || {};
        // Mark complete
        setPipelineStatus(prev => {
          const updated = { ...prev };
          for (const [fid, status] of Object.entries(updated)) {
            if (status.taskId === taskId) {
              updated[fid] = {
                ...status,
                progress: 100,
                committed: true,
                committing: false,
                stats: {
                  ...status.stats,
                  entities_found:      commitResult.nodes_created         ?? status.stats?.entities_found,
                  relationships_found: commitResult.relationships_created ?? status.stats?.relationships_found,
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
        setError(`[ERROR] Commit failed: ${err.message}`);
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
      return { text: 'Loading to Neo4j…', bg: '#FFF8E1', color: '#F57F17' };
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

  const getStageLabel = (stageId) => {
    const stage = PIPELINE_STAGES.find(s => s.id === stageId);
    return stage ? stage.label : stageId;
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

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

      {/* Header */}
      <div style={{
        marginBottom: '10px',
      }}>
        <h2 style={{ fontSize: '14px', fontWeight: '700', color: C.textPrimary, margin: '0 0 2px 0' }}>
          Data Import Pipeline
        </h2>
        <p style={{ fontSize: '10px', color: C.textMuted, margin: 0 }}>
          Upload and process data files through the semantic ontology pipeline
        </p>
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
          {PIPELINE_STAGES.map((stage, idx) => {
            const filesAtStage = files.filter(f => {
              const status = pipelineStatus[f.fileId];
              const currentStage = status?.stage || 'upload';
              return currentStage === stage.id;
            }).length;
            const isSelected = selectedStage === stage.id;

            // Calculate max current stage index
            let maxCurrentIdx = -1;
            const hasStartedFiles = Array.from(startedFiles).length > 0;
            if (hasStartedFiles) {
              const currentIndices = Array.from(startedFiles)
                .map(fId => {
                  const s = pipelineStatus[fId];
                  return PIPELINE_STAGES.findIndex(st => st.id === (s?.stage || 'upload'));
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
                {idx < PIPELINE_STAGES.length - 1 && (
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
              const stage = PIPELINE_STAGES.find(s => s.id === selectedStage);
              const stageFiles = files.filter(f => {
                const status = pipelineStatus[f.fileId];
                const currentStage = status?.stage || 'upload';
                return currentStage === selectedStage;
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
                    {selectedStage === 'upload' && (
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
                      No files in this stage yet
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
            <span style={{ fontSize: '18px' }}>⚠️</span>
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
        accept={SUPPORTED_FORMATS.map(f => f.ext).join(',')}
        style={{ display: 'none' }}
      />

      {/* Ontology Alignment & Start Pipeline */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '4px',
        padding: '6px 10px',
        marginBottom: '8px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
      }}>
        <label style={{
          fontSize: '10px',
          fontWeight: '600',
          color: C.textPrimary,
          whiteSpace: 'nowrap',
        }}>
          Ontology Alignment:
        </label>
        <select
          value={selectedOntology}
          onChange={(e) => setSelectedOntology(e.target.value)}
          style={{
            flex: 1,
            padding: '4px 8px',
            fontSize: '10px',
            border: `1px solid ${C.borderDark}`,
            borderRadius: '3px',
            background: C.bg,
            color: C.textPrimary,
            cursor: 'pointer',
            maxWidth: '400px',
          }}
          title="Select ontology mapping. STEP uses AP242-MBD3D automatically. CSV/Excel require a mapping."
        >
          <option key="auto" value="">No explicit mapping (use backend rules)</option>
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
        <span style={{ fontSize: '9px', color: C.textMuted }}>
          {selectedOntology || '(none selected)'}
        </span>
        <button
          onClick={startAllImports}
          disabled={files.filter(f => !startedFiles.has(f.fileId)).length === 0}
          style={{
            marginLeft: 'auto',
            padding: '4px 12px',
            background: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? C.textMuted : C.green,
            color: '#fff',
            border: 'none',
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: '700',
            cursor: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? 'not-allowed' : 'pointer',
            opacity: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          ▶ Start Pipeline
        </button>
      </div>

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
        <strong style={{ color: C.textPrimary }}>Alignment guidance:</strong>{' '}
        {mappingFileTypeContext === 'step' && 'STEP files use AP242-MBD3D mapping automatically.'}
        {(mappingFileTypeContext === 'csv' || mappingFileTypeContext === 'excel') && 'CSV/Excel require a selected ontology mapping before start.'}
        {(mappingFileTypeContext === 'json' || mappingFileTypeContext === 'xml') && 'JSON/XML can auto-generate OWL/TTL if no mapping is selected.'}
        {mappingFileTypeContext === 'ontology' && 'OWL/RDF/TTL are imported directly as ontology content (as-is).'}
        {!mappingFileTypeContext && 'Select files to see file-type specific alignment guidance.'}
        {requiredMappings.length > 0 && (
          <span> Required mapping for current file type: {requiredMappings.join(', ')}.</span>
        )}
      </div>

      {/* Data table */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        style={{
          background: C.surface,
          border: `1px solid ${dragActive ? C.primary : C.border}`,
          borderRadius: '6px',
          overflow: 'hidden',
          transition: 'border-color 0.15s',
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
          <div
            onClick={() => fileInputRef.current?.click()}
            style={{
              padding: '40px 20px',
              textAlign: 'center',
              color: C.textMuted,
              fontSize: '11px',
              background: dragActive ? C.primaryLight : C.bg,
              borderRadius: '0 0 6px 6px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '120px',
              gap: '8px',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}>
            <div style={{ fontSize: '28px', opacity: 0.5 }}>📁</div>
            <div style={{ fontWeight: '500', color: C.textSec }}>No files uploaded yet</div>
            <div style={{ fontSize: '10px', color: C.textMuted }}>
              Drag and drop files here or click to browse
            </div>
            <div style={{
              marginTop: '8px',
              fontSize: '9px',
              color: C.textMuted,
              maxWidth: '400px',
              lineHeight: '1.4'
            }}>
              Supported: CSV, JSON, STEP (.stp/.step/.stpx), XML, XSD, XMI, OWL, RDF/XML, TTL, Excel
            </div>
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
                        whiteSpace: 'nowrap'
                      }}>
                        🧬 {file.prefix}
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
                          ({status.stats.ontology_mapping === 'auto' ? '🔄 Auto' : '✓ ' + status.stats.ontology_mapping})
                        </span>
                      )}
                      {/* SHACL status indicator */}
                      {typeof status.shaclConforms !== 'undefined' && status.shaclConforms !== null && (
                        <span style={{ fontSize: '10px', fontWeight: '700', marginLeft: '8px', color: status.shaclConforms ? C.green : C.orange }}>
                          {status.shaclConforms ? 'SHACL ✓' : 'SHACL ✖'}
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
                    {!isStarted && status.stage === 'upload' && (
                      <button
                        onClick={() => {
                          setStartedFiles(prev => new Set([...prev, fileId]));
                          startImport(file);
                        }}
                        style={{
                          padding: '6px 10px',
                          background: C.primary,
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
                        title="Start import"
                      >
                        <Play size={12} /> Start
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
                          apiClient.get(buildUrl(`/api/v1/import/pre-commit/${status.taskId}`), { timeout: 15000 })
                            .then(r => setPreCheck({ loading: false, ...r.data }))
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
                        ⬆ Load to Neo4j
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
                        [WAIT] Loading to Neo4j…
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
                      }}>
                        ✓ Committed
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
                  disabled={files.filter(f => !startedFiles.has(f.fileId)).length === 0}
                  style={{
                    padding: '4px 10px',
                    background: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? C.textMuted : C.green,
                    color: '#fff',
                    border: 'none',
                    borderRadius: '3px',
                    fontSize: '10px',
                    fontWeight: '600',
                    cursor: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? 'not-allowed' : 'pointer',
                    opacity: files.filter(f => !startedFiles.has(f.fileId)).length === 0 ? 0.5 : 1,
                  }}>
                  Start All Imports
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
                  Checking Neo4j connectivity and task state…
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              )}
              {!preCheck?.loading && preCheck && (
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, color: preCheck.ready ? '#067647' : '#B42318' }}>
                    {preCheck.ready ? '[OK] Ready to commit' : '[ERROR] Cannot commit'}
                  </span>
                  {preCheck.checks?.neo4j && (
                    <span style={{ color: preCheck.checks.neo4j.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.neo4j.ok ? '✔' : '✘'} Neo4j: {preCheck.checks.neo4j.message || (preCheck.checks.neo4j.ok ? 'Connected' : 'Unreachable')}
                    </span>
                  )}
                  {preCheck.checks?.task && (
                    <span style={{ color: preCheck.checks.task.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.task.ok ? '✔' : '✘'} Task: {preCheck.checks.task.status}
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
                {preCheck?.loading ? '[WAIT] Checking…' : '[OK] Confirm Import'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
