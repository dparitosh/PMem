import React, { useState, useCallback } from 'react';
import GraphSchemaLayer from './GraphSchemaLayer';
import GraphInstanceLayer from './GraphInstanceLayer';
import '../CSS/GraphHEB.css';
import { logger } from '../utils/logger';

/**
 * GraphLayeredView Component
 * 
 * Manages the visualization of two separate graph layers:
 * 1. SCHEMA LAYER (Ontology) - Hierarchical view of classes and relationships
 * 2. INSTANCE LAYER (Contextual) - Organic network view of real entities
 * 
 * Features:
 * - Toggle between schema and instance views
 * - Toggle to combined view (if needed)
 * - Layer-specific styling and color coding
 * - Mode switcher UI with clear visual feedback
 */

export const GraphLayeredView = ({ selectedNode = null, highlightedNodes = [] }) => {
  const [viewMode, setViewMode] = useState('schema'); // 'schema', 'instance', or 'combined'
  const [selectedNodeData, setSelectedNodeData] = useState(null);

  const handleNodeClick = useCallback((nodeData) => {
    setSelectedNodeData(nodeData);
    logger.render('Selected layered graph node:', nodeData);
  }, []);

  return (
    <div className="graph-layered-view" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Control Toolbar */}
      <div 
        className="layer-control-toolbar"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '12px 16px',
          background: '#f5f5f5',
          borderBottom: '2px solid #ddd',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}
      >
        {/* Mode Switcher */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, fontSize: '13px', color: '#333' }}>View Mode:</span>
          
          <button
            onClick={() => setViewMode('schema')}
            style={{
              padding: '6px 14px',
              border: viewMode === 'schema' ? '2px solid #4A90E2' : '1px solid #ddd',
              background: viewMode === 'schema' ? '#EBF5FB' : '#fff',
              color: viewMode === 'schema' ? '#004B87' : '#666',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: viewMode === 'schema' ? 600 : 500,
              fontSize: '12px',
              transition: 'all 0.2s'
            }}
            title="View ontology schema with hierarchical layout"
          >
            📋 Schema (Ontology)
          </button>

          <button
            onClick={() => setViewMode('instance')}
            style={{
              padding: '6px 14px',
              border: viewMode === 'instance' ? '2px solid #27AE60' : '1px solid #ddd',
              background: viewMode === 'instance' ? '#E8F8F5' : '#fff',
              color: viewMode === 'instance' ? '#1E8449' : '#666',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: viewMode === 'instance' ? 600 : 500,
              fontSize: '12px',
              transition: 'all 0.2s'
            }}
            title="View real entities and business processes"
          >
            🌐 Instance (Contextual)
          </button>

          <button
            onClick={() => setViewMode('combined')}
            style={{
              padding: '6px 14px',
              border: viewMode === 'combined' ? '2px solid #9B59B6' : '1px solid #ddd',
              background: viewMode === 'combined' ? '#F4ECF7' : '#fff',
              color: viewMode === 'combined' ? '#6C3483' : '#666',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: viewMode === 'combined' ? 600 : 500,
              fontSize: '12px',
              transition: 'all 0.2s',
              opacity: 0.5
            }}
            disabled
            title="Combined view (coming soon)"
          >
            🔗 Combined (Soon)
          </button>
        </div>

        {/* Info Display */}
        <div style={{ marginLeft: 'auto', fontSize: '12px', color: '#666' }}>
          {viewMode === 'schema' && '📊 Viewing ontology class hierarchy'}
          {viewMode === 'instance' && '📊 Viewing real entities and processes'}
          {viewMode === 'combined' && '📊 Viewing combined layers'}
        </div>
      </div>

      {/* Legend */}
      <div 
        className="layer-legend"
        style={{
          display: 'flex',
          gap: '24px',
          padding: '8px 16px',
          background: '#fafafa',
          borderBottom: '1px solid #eee',
          fontSize: '11px',
          color: '#666'
        }}
      >
        {viewMode === 'schema' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#4A90E2' }}></div>
              <span>OntologyClass</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#7F8C8D' }}></div>
              <span>Properties (Object/Datatype)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#E74C3C' }}></div>
              <span>Constraints</span>
            </div>
          </>
        )}
        
        {viewMode === 'instance' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#27AE60' }}></div>
              <span>Entity Instances</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#3498DB' }}></div>
              <span>Processes</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#E74C3C' }}></div>
              <span>Events/Transactions</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#F39C12' }}></div>
              <span>Contextual (Time/Source)</span>
            </div>
          </>
        )}
      </div>

      {/* Main Visualization Area */}
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        {viewMode === 'schema' && (
          <GraphSchemaLayer 
            onNodeClick={handleNodeClick}
            selectedNode={selectedNodeData}
            highlightedNodes={highlightedNodes}
          />
        )}
        
        {viewMode === 'instance' && (
          <GraphInstanceLayer 
            onNodeClick={handleNodeClick}
            selectedNode={selectedNodeData}
            highlightedNodes={highlightedNodes}
          />
        )}

        {viewMode === 'combined' && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999' }}>
            Combined view coming soon
          </div>
        )}
      </div>

      {/* Selected Node Info Panel */}
      {selectedNodeData && (
        <div 
          className="node-info-panel"
          style={{
            borderTop: '1px solid #ddd',
            background: '#fff',
            padding: '12px 16px',
            fontSize: '11px',
            maxHeight: '150px',
            overflow: 'auto'
          }}
        >
          <div style={{ marginBottom: '8px', fontWeight: 600, color: '#333' }}>
            Selected: {selectedNodeData.name}
          </div>
          <div style={{ color: '#666', marginBottom: '4px' }}>
            <strong>Label:</strong> {selectedNodeData.label}
          </div>
          <div style={{ color: '#666', marginBottom: '4px' }}>
            <strong>Layer:</strong> <span style={{ color: viewMode === 'schema' ? '#4A90E2' : '#27AE60', fontWeight: 600 }}>
              {viewMode === 'schema' ? 'Schema' : 'Instance'}
            </span>
          </div>
          {selectedNodeData.properties && Object.keys(selectedNodeData.properties).length > 0 && (
            <div style={{ marginTop: '8px' }}>
              <strong>Properties:</strong>
              <pre style={{ background: '#f5f5f5', padding: '6px', borderRadius: '3px', overflow: 'auto', maxHeight: '80px', fontSize: '10px' }}>
                {JSON.stringify(selectedNodeData.properties, null, 2).substring(0, 300)}
              </pre>
            </div>
          )}
          <button
            onClick={() => setSelectedNodeData(null)}
            style={{
              marginTop: '8px',
              padding: '4px 8px',
              background: '#f5f5f5',
              border: '1px solid #ddd',
              borderRadius: '3px',
              cursor: 'pointer',
              fontSize: '11px'
            }}
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
};

export default GraphLayeredView;
