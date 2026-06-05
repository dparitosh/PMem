/**
 * Railway Pipeline Visualization Component
 * ═══════════════════════════════════════════════════════════════
 * Displays data import pipeline as a railway network with:
 * - Real-time stage progress (🟢 complete, 🟡 running, ⚪ pending, 🔴 failed)
 * - Curved connections between stages
 * - Data flow metrics
 * - Performance timing
 * - Expandable stage details
 * 
 * Usage:
 *   <RailwayPipeline taskId="abc-123-def" />
 */

import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import config from '../config';
import './RailwayPipeline.css';

const RailwayPipeline = ({ taskId, autoRefresh = true, refreshInterval = 500 }) => {
  const [pipelineData, setPipelineData] = useState(null);
  const [expandedStage, setExpandedStage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch task status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await axios.get(`${config.apiUrl}/import-task/${taskId}`, {
          timeout: 5000,
        });
        setPipelineData(response.data);
        setError(null);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    };

    if (taskId) {
      fetchStatus();
    }

    // Auto-refresh if enabled and not complete
    if (autoRefresh && pipelineData?.status !== 'completed' && pipelineData?.status !== 'failed') {
      const interval = setInterval(fetchStatus, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [taskId, autoRefresh, refreshInterval, pipelineData?.status]);

  if (loading) {
    return (
      <div className="railway-container loading">
        <div className="spinner">⚙️ Loading pipeline...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="railway-container error">
        <div className="error-message">❌ Error: {error}</div>
      </div>
    );
  }

  if (!pipelineData) {
    return (
      <div className="railway-container error">
        <div className="error-message">❌ No task data found</div>
      </div>
    );
  }

  // Normalize pipeline stages
  const stages = [
    {
      id: 1,
      name: 'Upload',
      status: pipelineData.current_stage === 'upload' ? 'running' : 'complete',
      progress: pipelineData.current_stage === 'upload' ? pipelineData.progress : 100,
      stats: `${(pipelineData.file_size_mb || 0).toFixed(1)} MB`,
      details: pipelineData.filename,
    },
    {
      id: 2,
      name: 'Parse',
      status: pipelineData.current_stage === 'convert' ? 'running' : 
              pipelineData.current_stage !== 'upload' ? 'complete' : 'pending',
      progress: pipelineData.current_stage === 'convert' ? pipelineData.progress : 
                pipelineData.current_stage !== 'upload' ? 100 : 0,
      stats: `${pipelineData.stats?.entities_found || 0} entities`,
      details: pipelineData.stats?.entities_found ? `Parsed ${pipelineData.stats.entities_found} entities from ${pipelineData.file_type}` : 'Waiting...',
    },
    {
      id: 3,
      name: 'Map',
      status: pipelineData.current_stage === 'map' ? 'running' : 
              ['validate', 'enrich', 'load', 'verify'].includes(pipelineData.current_stage) ? 'complete' : 'pending',
      progress: pipelineData.current_stage === 'map' ? pipelineData.progress : 
                ['validate', 'enrich', 'load', 'verify'].includes(pipelineData.current_stage) ? 100 : 0,
      stats: `${pipelineData.stats?.entities_mapped || 0} mapped`,
      details: `${pipelineData.stats?.ontology_mapping || 'auto-detect'} mapping`,
    },
    {
      id: 4,
      name: 'Validate',
      status: pipelineData.current_stage === 'validate' ? 'running' : 
              ['enrich', 'load', 'verify'].includes(pipelineData.current_stage) ? 'complete' : 'pending',
      progress: pipelineData.current_stage === 'validate' ? pipelineData.progress : 
                ['enrich', 'load', 'verify'].includes(pipelineData.current_stage) ? 100 : 0,
      stats: `${pipelineData.stats?.validation_status || '?'}`,
      details: pipelineData.stats?.validation_status ? `Status: ${pipelineData.stats.validation_status}` : 'Pending validation...',
    },
    {
      id: 5,
      name: 'Enrich',
      status: pipelineData.current_stage === 'enrich' ? 'running' : 
              ['load', 'verify'].includes(pipelineData.current_stage) ? 'complete' : 'pending',
      progress: pipelineData.current_stage === 'enrich' ? pipelineData.progress : 
                ['load', 'verify'].includes(pipelineData.current_stage) ? 100 : 0,
      stats: `${pipelineData.stats?.relationships_found || 0} rels`,
      details: `${pipelineData.stats?.entities_transformed || 0} enriched, ${pipelineData.stats?.relationships_found || 0} relationships`,
    },
    {
      id: 6,
      name: 'Load',
      status: pipelineData.current_stage === 'load' ? 'running' : 
              pipelineData.current_stage === 'verify' ? 'complete' : 'pending',
      progress: pipelineData.current_stage === 'load' ? pipelineData.progress : 
                pipelineData.current_stage === 'verify' ? 100 : 0,
      stats: `${pipelineData.stats?.entities_ingested || 0} nodes`,
      details: `${pipelineData.stats?.entities_ingested || 0} entities created, ${pipelineData.stats?.relationships_created || 0} relationships created`,
    },
    {
      id: 7,
      name: 'Verify',
      status: pipelineData.current_stage === 'verify' ? 'running' : 
              pipelineData.status === 'completed' ? 'complete' : 
              pipelineData.status === 'failed' ? 'failed' : 'pending',
      progress: pipelineData.current_stage === 'verify' ? pipelineData.progress : 
                pipelineData.status === 'completed' ? 100 : 
                pipelineData.status === 'failed' ? 0 : 0,
      stats: `${pipelineData.stats?.verification_status || '?'}`,
      details: pipelineData.error ? `❌ ${pipelineData.error}` : `Status: ${pipelineData.stats?.verification_status || 'pending'}`,
    },
  ];

  // Status emoji
  const statusEmoji = (status) => {
    switch (status) {
      case 'complete':
        return '🟢';
      case 'running':
        return '🟡';
      case 'pending':
        return '⚪';
      case 'failed':
        return '🔴';
      default:
        return '⚪';
    }
  };

  // Color for progress bar
  const progressColor = (status) => {
    switch (status) {
      case 'complete':
        return '#10b981'; // green
      case 'running':
        return '#f59e0b'; // amber
      case 'pending':
        return '#d1d5db'; // gray
      case 'failed':
        return '#ef4444'; // red
      default:
        return '#d1d5db';
    }
  };

  return (
    <div className="railway-container">
      <div className="railway-header">
        <h2>🚂 Data Import Pipeline</h2>
        <div className="pipeline-info">
          <span className="task-id">Task: {taskId.slice(0, 8)}...</span>
          <span className="status-badge" style={{
            backgroundColor: pipelineData.status === 'completed' ? '#10b981' :
                             pipelineData.status === 'failed' ? '#ef4444' :
                             pipelineData.status === 'processing' ? '#f59e0b' : '#d1d5db',
          }}>
            {pipelineData.status?.toUpperCase()}
          </span>
          <span className="timing">
            {pipelineData.started_at && new Date(pipelineData.started_at).toLocaleTimeString()}
          </span>
        </div>
      </div>

      <div className="railway-track">
        {/* SVG for connections */}
        <svg className="railway-connections" width="100%" height="180">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
              <polygon points="0 0, 10 3, 0 6" fill="#6b7280" />
            </marker>
          </defs>
          
          {/* Draw curved connections between stages */}
          {stages.map((stage, idx) => {
            if (idx < stages.length - 1) {
              const x1 = ((idx) / (stages.length - 1)) * (typeof window !== 'undefined' ? window.innerWidth - 100 : 0) + 50;
              const x2 = ((idx + 1) / (stages.length - 1)) * (typeof window !== 'undefined' ? window.innerWidth - 100 : 0) + 50;
              const y = 90;
              
              return (
                <g key={`connection-${idx}`}>
                  {/* Curved path */}
                  <path
                    d={`M ${x1} ${y} Q ${(x1 + x2) / 2} ${y - 30} ${x2} ${y}`}
                    stroke="#9ca3af"
                    strokeWidth="2"
                    fill="none"
                    strokeDasharray="5,5"
                    markerEnd="url(#arrowhead)"
                  />
                  {/* Data flow label */}
                  <text
                    x={(x1 + x2) / 2}
                    y={y - 40}
                    textAnchor="middle"
                    fontSize="11"
                    fill="#6b7280"
                    className="flow-label"
                  >
                    {stages[idx].stats}
                  </text>
                </g>
              );
            }
            return null;
          })}
        </svg>

        {/* Stage stations */}
        <div className="railway-stations">
          {stages.map((stage) => (
            <div
              key={`stage-${stage.id}`}
              className={`railway-station ${stage.status}`}
              onClick={() => setExpandedStage(expandedStage === stage.id ? null : stage.id)}
              title={stage.details}
            >
              {/* Station visual */}
              <div className="station-visual">
                <div className="station-circle" style={{ borderColor: progressColor(stage.status) }}>
                  <div className="status-emoji">{statusEmoji(stage.status)}</div>
                </div>
                
                {/* Progress ring */}
                <svg className="progress-ring" viewBox="0 0 100 100">
                  <circle
                    cx="50"
                    cy="50"
                    r="45"
                    fill="none"
                    stroke="#e5e7eb"
                    strokeWidth="4"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r="45"
                    fill="none"
                    stroke={progressColor(stage.status)}
                    strokeWidth="4"
                    strokeDasharray={`${stage.progress * 2.827} 282.7`}
                    strokeLinecap="round"
                    style={{ transition: 'stroke-dasharray 0.3s ease' }}
                  />
                  <text x="50" y="55" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#1f2937">
                    {stage.progress}%
                  </text>
                </svg>
              </div>

              {/* Station label */}
              <div className="station-label">
                <div className="stage-name">{stage.name}</div>
                <div className="stage-stats">{stage.stats}</div>
              </div>

              {/* Expandable details */}
              {expandedStage === stage.id && (
                <div className="station-details">
                  <div className="details-content">
                    <div className="detail-line">
                      <span className="detail-label">Status:</span>
                      <span className="detail-value">{stage.status}</span>
                    </div>
                    <div className="detail-line">
                      <span className="detail-label">Progress:</span>
                      <span className="detail-value">{stage.progress}%</span>
                    </div>
                    <div className="detail-line">
                      <span className="detail-label">Info:</span>
                      <span className="detail-value">{stage.details}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Summary statistics */}
      <div className="pipeline-summary">
        <div className="summary-card">
          <div className="summary-label">Total Entities</div>
          <div className="summary-value">{pipelineData.stats?.entities_found || 0}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Ingested</div>
          <div className="summary-value">{pipelineData.stats?.entities_ingested || 0}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Relationships</div>
          <div className="summary-value">{pipelineData.stats?.relationships_created || 0}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Duration</div>
          <div className="summary-value">
            {pipelineData.started_at && pipelineData.completed_at
              ? `${Math.round((new Date(pipelineData.completed_at) - new Date(pipelineData.started_at)) / 1000)}s`
              : pipelineData.started_at
              ? `${Math.round((new Date() - new Date(pipelineData.started_at)) / 1000)}s`
              : '-'}
          </div>
        </div>
      </div>

      {/* Error display */}
      {pipelineData.error && (
        <div className="pipeline-error">
          <div className="error-header">❌ Import Failed</div>
          <div className="error-content">{pipelineData.error}</div>
        </div>
      )}

      {/* Success message */}
      {pipelineData.status === 'completed' && (
        <div className="pipeline-success">
          <div className="success-header">✅ Import Completed Successfully</div>
          <div className="success-content">
            {pipelineData.stats?.entities_ingested} entities and {pipelineData.stats?.relationships_created} relationships
            loaded to Neo4j knowledge graph
          </div>
        </div>
      )}
    </div>
  );
};

export default RailwayPipeline;
