import React, { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toReactFlowElements, fromReactFlowElements } from '../../adapters/reactFlowAdapter';

export default function ReactFlowDiagramCanvas({ graph = {}, selectedId, onSelect, onGraphChange, onConnect }) {
  const { nodes, edges } = useMemo(() => toReactFlowElements(graph), [graph]);

  const handleNodesChange = useCallback((changes) => {
    const nextNodes = applyNodeChanges(changes, nodes);
    onGraphChange?.(fromReactFlowElements(nextNodes, edges));
  }, [edges, nodes, onGraphChange]);

  const handleEdgesChange = useCallback((changes) => {
    const nextEdges = applyEdgeChanges(changes, edges);
    onGraphChange?.(fromReactFlowElements(nodes, nextEdges));
  }, [edges, nodes, onGraphChange]);

  const handleConnect = useCallback((connection) => {
    const nextEdges = addEdge({ ...connection, type: 'smoothstep', label: 'TRACE_TO' }, edges);
    onConnect?.(connection);
    onGraphChange?.(fromReactFlowElements(nodes, nextEdges));
  }, [edges, nodes, onConnect, onGraphChange]);

  return (
    <div className="react-flow-diagram-canvas">
      <ReactFlow
        nodes={nodes.map((node) => ({ ...node, selected: node.id === selectedId }))}
        edges={edges}
        fitView
        nodesDraggable
        nodesConnectable
        elementsSelectable
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeClick={(_, node) => onSelect?.(node.data)}
        onEdgeClick={(_, edge) => onSelect?.(edge.data)}
      >
        <Background gap={18} color="#233142" />
        <MiniMap pannable zoomable nodeStrokeWidth={3} />
        <Controls showInteractive />
      </ReactFlow>
    </div>
  );
}


