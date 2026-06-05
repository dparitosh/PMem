import React, { useState, useRef, useEffect } from 'react';
import { X, Play, RefreshCw } from 'lucide-react';

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

const SUPPORTED_FORMATS = [
  { ext: '.csv', name: 'CSV' },
  { ext: '.json', name: 'JSON' },
  { ext: '.html', name: 'HTML' },
  { ext: '.htm', name: 'HTML' },
  { ext: '.owl', name: 'OWL' },
  { ext: '.rdf', name: 'RDF' },
  { ext: '.ttl', name: 'Turtle' },
  { ext: '.plmxml', name: 'PLMXML' },
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

const API_BASE_URL = 'http://localhost:8000';

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
  const fileInputRef = useRef(null);

  // Ontology mapping selection
  const [availableOntologies, setAvailableOntologies] = useState([]);
  const [selectedOntology, setSelectedOntology] = useState('');

  // Fetch available ontologies dynamically from Neo4j
  useEffect(() => {
    const fetchOntologies = async () => {
      try {
        // Fetch from backend - gets dynamic list from Neo4j + fallback
        const res = await fetch(`${API_BASE_URL}/ontologies/available`);
        if (res.ok) {
          const data = await res.json();
          const ontologies = data.ontologies.map(ont => ({
            id: ont.id,
            name: ont.name,
            file: ont.name, // Use name as file reference
            source: ont.source,
            usage_count: ont.usageCount,
            last_used: ont.lastUsed,
          }));
          setAvailableOntologies(ontologies);
          return;
        }
      } catch (_) { /* fallback below */ }
      
      // If backend fails, show no options (user must fix backend)
      setAvailableOntologies([]);
    };
    fetchOntologies();
  }, []);

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


  // Map file extension to ontology id (dynamic, not hardcoded)
  const getOntologyForFile = (fileName) => {
    const ext = '.' + fileName.split('.').pop().toLowerCase();
    // Map STEP extensions to ap242
    if ([".stp", ".step", ".stpx"].includes(ext)) {
      // Find ap242 ontology in availableOntologies
      const ap242 = availableOntologies.find(o => (o.prefix || o.type || '').toLowerCase().includes('ap242'));
      return ap242 ? ap242.id : '';
    }
    // Add more mappings as needed
    return '';
  };

  const startImport = async (file) => {
    const fileId = file.fileId;
    setPipelineStatus(prev => ({ ...prev, [fileId]: { stage: 'upload', progress: 0, message: 'Uploading...' } }));

    try {
      const formData = new FormData();
      formData.append('file', file.fileObj);
      // If user selected auto-detect, use mapping
      let ontologyToUse = selectedOntology;
      if (!ontologyToUse) {
        ontologyToUse = getOntologyForFile(file.name);
      }
      formData.append('ontology_mapping', ontologyToUse);

      const uploadRes = await fetch(`${API_BASE_URL}/data-import/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!uploadRes.ok) {
        throw new Error(`Upload failed: ${uploadRes.status}`);
      }

      const uploadData = await uploadRes.json();
      const taskId = uploadData.task_id;

      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: { 
          ...prev[fileId],
          taskId,
          stage: 'convert',
          message: 'Converting file...'
        }
      }));

      await pollPipelineProgress(taskId, fileId);
    } catch (err) {
      setPipelineStatus(prev => ({
        ...prev,
        [fileId]: { 
          ...prev[fileId], 
          stage: 'error', 
          message: err.message,
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
        const res = await fetch(`${API_BASE_URL}/data-import/status/${taskId}`);
        if (!res.ok) throw new Error('Status check failed');

        const data = await res.json();
        
        setPipelineStatus(prev => ({
          ...prev,
          [fileId]: {
            taskId,
            stage: data.current_stage,
            progress: data.progress,
            message: data.message,
            stats: data.stats,
            status: data.status,
            error: data.error ? true : false,
            completedAt: data.status === 'completed' ? new Date().toLocaleTimeString() : null,
          }
        }));

        // Auto-set preview data when verify stage or completed is reached
        if (data.current_stage === 'verify' || data.status === 'completed') {
          setPreviewData(data.preview || data);
          setPreviewTaskId(taskId);
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
    const filesToImport = files.filter(f => !startedFiles.has(f.fileId));
    if (filesToImport.length === 0) {
      setError('All files have already been started');
      return;
    }

    setStartedFiles(prev => new Set([...prev, ...filesToImport.map(f => f.fileId)]));
    
    for (const file of filesToImport) {
      startImport(file);
    }
  };

  const commitImport = async (taskId) => {
    try {
      // Data was already ingested during pipeline; commit endpoint confirms/finalizes
      const commitRes = await fetch(`${API_BASE_URL}/data-import/commit/${taskId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      // If commit endpoint doesn't exist, treat the already-completed pipeline as success
      if (!commitRes.ok && commitRes.status !== 404) {
        throw new Error(`Commit failed: ${commitRes.status}`);
      }

      // Mark file as fully committed in UI
      setPipelineStatus(prev => {
        const updated = { ...prev };
        for (const [fid, status] of Object.entries(updated)) {
          if (status.taskId === taskId) {
            updated[fid] = { ...status, progress: 100, committed: true };
          }
        }
        return updated;
      });
      setConfirmingImport(null);
      setError(null);
    } catch (err) {
      setError(`❌ Commit failed: ${err.message}`);
    }
  };

  const removeFile = (fileId) => {
    const fileStatus = pipelineStatus[fileId];
    
    // Cancel task if in progress
    if (fileStatus?.taskId && fileStatus?.status === 'processing') {
      fetch(`${API_BASE_URL}/data-import/cancel/${fileStatus.taskId}`, {
        method: 'POST',
      }).catch(err => console.warn('Cancel failed:', err));
    }

    setFiles(prev => prev.filter(f => f.fileId !== fileId));
    setStartedFiles(prev => {
      const updated = new Set(prev);
      updated.delete(fileId);
      return updated;
    });
  };

  const getStatusBadge = (stage, progress, error) => {
    if (error) {
      return { text: 'Error', bg: '#FFEBEE', color: C.red };
    }
    if (stage === 'verify' && progress >= 75) {
      return { text: 'Ready', bg: '#E3F2FD', color: C.primary };
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
          border: `1px solid ${C.red}`,
          borderRadius: '6px',
          padding: '12px 16px',
          marginBottom: '20px',
          fontSize: '12px',
          color: C.red,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{
              background: 'transparent',
              border: 'none',
              color: C.red,
              cursor: 'pointer',
              padding: '0',
              fontSize: '16px',
            }}
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
          Ontology Alignment <span style={{ fontSize: '9px', color: C.textMuted }}>(optional)</span>:
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
          title="Select an ontology or leave empty to auto-detect from file format"
        >
          <option value="">Auto-detect from file format</option>
          {Array.from(new Map(availableOntologies.map(o => [o.id, o])).values()).map(ont => {
            // Show prefix/type if available
            const prefix = ont.prefix || ont.type || '';
            let label = ont.name;
            if (prefix) label += ` [${prefix}]`;
            if (ont.usage_count) label += ` (used ${ont.usage_count}x)`;
            if (ont.source === 'dynamic') label += ' ✓ in Neo4j';
            return (
              <option key={ont.id} value={ont.id}>
                {label}
              </option>
            );
          })}
        </select>
        <span style={{ fontSize: '9px', color: C.textMuted }}>
          {selectedOntology ? availableOntologies.find(o => o.id === selectedOntology)?.file || selectedOntology : '(auto)'}
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

      {/* Data table */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        overflow: 'hidden',
      }}>
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
            padding: '20px 10px',
            textAlign: 'center',
            color: C.textMuted,
            fontSize: '11px',
          }}>
            No files uploaded yet
          </div>
        ) : (
          <>
            {/* Table rows */}
            {files.map(file => {
              const fileId = file.fileId;
              const status = pipelineStatus[fileId] || { stage: 'upload', progress: 0 };
              const isStarted = startedFiles.has(fileId);
              const statusBadge = getStatusBadge(status.stage, status.progress, status.error);

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
                  <div title={file.name} style={{
                    fontWeight: '500',
                    color: C.textPrimary,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {file.name}
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
                    {isStarted && status.stage !== 'verify' && status.status !== 'completed' && status.progress < 75 && (
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
                    {isStarted && (status.stage === 'verify' || status.status === 'completed') && !status.error && !status.committed && (
                      <button
                        onClick={() => {
                          setConfirmingImport(status.taskId);
                          setPreviewTaskId(status.taskId);
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
                        title="Review and commit import"
                      >
                        ✓ Commit
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
                <div style={{ color: C.textMuted }}>
                  {files.length} file{files.length !== 1 ? 's' : ''} • {startedFiles.size} processing
                </div>
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
                    key={idx}
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
                      {(previewData.columns || []).slice(0, 5).map((col, idx) => (
                        <th
                          key={idx}
                          style={{
                            padding: '8px',
                            textAlign: 'left',
                            fontWeight: '600',
                            color: C.textPrimary,
                            borderRight: idx < 4 ? `1px solid ${C.border}` : 'none',
                          }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(previewData.sample_rows || []).map((row, rowIdx) => (
                      <tr key={rowIdx} style={{ borderBottom: `1px solid ${C.border}` }}>
                        {(previewData.columns || []).slice(0, 5).map((col, colIdx) => (
                          <td
                            key={colIdx}
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
                style={{
                  padding: '8px 16px',
                  background: C.green,
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                ✓ Confirm Import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
