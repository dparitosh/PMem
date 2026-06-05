import React, { useMemo, useState } from 'react';
import apiClient from '../services/apiClient';
import { API } from '../config';
import './DigitalThreadTracer.css';

const sampleComponents = ['Rotor Shaft', 'Motor Housing', 'Bearing', 'Assembly'];

const getNodeName = (node) => (
  node?.name ||
  node?.properties?.name ||
  node?.FileName ||
  node?.properties?.FileName ||
  node?.id ||
  node?.elementId ||
  'Unnamed node'
);

const getRelationshipName = (rel) => (
  rel?.relationship ||
  rel?.type ||
  rel?.label ||
  rel?.name ||
  'RELATED_TO'
);

const formatJson = (value) => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const DigitalThreadTracer = () => {
  const [componentName, setComponentName] = useState('Rotor Shaft');
  const [isLoading, setIsLoading] = useState(false);
  const [traceData, setTraceData] = useState(null);
  const [error, setError] = useState('');
  const [expandedSection, setExpandedSection] = useState('summary');

  const nodes = useMemo(() => traceData?.nodes || [], [traceData]);
  const relationships = useMemo(() => traceData?.relationships || [], [traceData]);

  const handleTrace = async (event) => {
    event.preventDefault();

    const trimmedName = componentName.trim();
    if (!trimmedName) {
      setError('Enter a component, part, requirement, or file name to trace.');
      return;
    }

    setIsLoading(true);
    setError('');
    setTraceData(null);

    try {
      const response = await apiClient.post(API.integration.digitalThreadTrace, {
        message: trimmedName,
        session_id: `trace-${Date.now()}`,
      });
      setTraceData(response.data);
      setExpandedSection('summary');
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.error || err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const downloadTrace = () => {
    if (!traceData) return;

    const blob = new Blob([formatJson(traceData)], { type: 'application/json' });
    const element = document.createElement('a');
    element.href = URL.createObjectURL(blob);
    element.download = `digital-thread-${componentName.trim() || 'trace'}.json`;
    document.body.appendChild(element);
    element.click();
    element.remove();
    URL.revokeObjectURL(element.href);
  };

  const renderSectionButton = (id, label, count) => (
    <button
      type="button"
      className={`trace-section-button ${expandedSection === id ? 'active' : ''}`}
      onClick={() => setExpandedSection(id)}
    >
      <span>{label}</span>
      {typeof count === 'number' && <strong>{count}</strong>}
    </button>
  );

  return (
    <div className="digital-thread-tracer">
      <div className="tracer-header">
        <div>
          <h2>Digital Thread Traceability</h2>
          <p>Trace an entity across connected graph context using the backend digital-thread service.</p>
        </div>
        {traceData && (
          <button type="button" onClick={downloadTrace} className="download-button">
            Download JSON
          </button>
        )}
      </div>

      <form onSubmit={handleTrace} className="trace-form">
        <label htmlFor="componentName">Entity</label>
        <input
          id="componentName"
          type="text"
          value={componentName}
          onChange={(event) => setComponentName(event.target.value)}
          placeholder="Rotor Shaft"
          disabled={isLoading}
          className="input-field"
        />
        <button type="submit" disabled={isLoading} className="trace-button">
          {isLoading ? 'Tracing...' : 'Trace'}
        </button>
      </form>

      <div className="sample-row">
        {sampleComponents.map((name) => (
          <button
            type="button"
            key={name}
            onClick={() => setComponentName(name)}
            className="sample-chip"
            disabled={isLoading}
          >
            {name}
          </button>
        ))}
      </div>

      {error && <div className="error-message">{error}</div>}

      {traceData && (
        <div className="trace-results">
          <div className="trace-meta">
            <span>Status: <strong>{traceData.status || 'complete'}</strong></span>
            <span>Nodes: <strong>{nodes.length}</strong></span>
            <span>Relationships: <strong>{relationships.length}</strong></span>
          </div>

          <div className="trace-layout">
            <div className="trace-sections">
              {renderSectionButton('summary', 'Summary')}
              {renderSectionButton('nodes', 'Nodes', nodes.length)}
              {renderSectionButton('relationships', 'Relationships', relationships.length)}
              {renderSectionButton('raw', 'Raw')}
            </div>

            <div className="trace-panel">
              {expandedSection === 'summary' && (
                <div className="summary-panel">
                  <h3>{componentName}</h3>
                  <pre>{traceData.answer || 'No narrative trace was returned by the backend.'}</pre>
                </div>
              )}

              {expandedSection === 'nodes' && (
                <div className="result-list">
                  {nodes.length === 0 ? (
                    <p className="empty-state">No nodes returned.</p>
                  ) : nodes.map((node, index) => (
                    <div className="result-card" key={node.elementId || node.id || index}>
                      <h4>{getNodeName(node)}</h4>
                      <code>{formatJson(node)}</code>
                    </div>
                  ))}
                </div>
              )}

              {expandedSection === 'relationships' && (
                <div className="result-list">
                  {relationships.length === 0 ? (
                    <p className="empty-state">No relationships returned.</p>
                  ) : relationships.map((rel, index) => (
                    <div className="result-card" key={rel.elementId || rel.id || index}>
                      <h4>{getRelationshipName(rel)}</h4>
                      <code>{formatJson(rel)}</code>
                    </div>
                  ))}
                </div>
              )}

              {expandedSection === 'raw' && (
                <pre className="raw-json">{formatJson(traceData)}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DigitalThreadTracer;
