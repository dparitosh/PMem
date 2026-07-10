import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  MarkerType,
  Position,
  Handle,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toReactFlowElements, fromReactFlowElements } from '../../adapters/reactFlowAdapter';

const CATEGORY_COLORS = {
  motivation: '#b45309',
  strategy: '#7c3aed',
  business: '#0f766e',
  application: '#005a9c',
  technology: '#166534',
  implementation: '#334155',
  other: '#64748b',
};

function semanticCategory(type = '') {
  const value = String(type).toLowerCase();
  if (/(requirement|constraint|goal|principle|driver|assessment|stakeholder)/.test(value)) return 'motivation';
  if (/(capability|courseofaction|resource|valuestream|strategy)/.test(value)) return 'strategy';
  if (/(business|operational|actor|role|performer|process|function)/.test(value)) return 'business';
  if (/(application|interface|dataobject|logical)/.test(value)) return 'application';
  if (/(technology|device|node|software|artifact|part|block|component|physical)/.test(value)) return 'technology';
  if (/(product|workpackage|deliverable|implementation|migration)/.test(value)) return 'implementation';
  return 'other';
}

function shapeForType(type = '') {
  const value = String(type).toLowerCase();
  if (/(package|folder)/.test(value)) return 'folder';
  if (/(view|diagram)/.test(value)) return 'view';
  if (/(requirement|constraint|goal|principle|driver|assessment)/.test(value)) return 'motivation';
  if (/(businessactor|actor|performer|role)/.test(value)) return 'actor';
  if (/(process|function|activity|capability|service)/.test(value)) return 'process';
  if (/(dataobject|artifact|document)/.test(value)) return 'document';
  if (/(node|device|systemsoftware|component|part|product)/.test(value)) return 'component';
  return 'element';
}

function iconForShape(shape) {
  switch (shape) {
    case 'folder': return '[+]';
    case 'view': return '<>';
    case 'motivation': return '!';
    case 'actor': return 'o';
    case 'process': return '[]';
    case 'document': return '#';
    case 'component': return '::';
    default: return '-';
  }
}

const SemanticNode = memo(({ data, selected }) => {
  const category = data?.metadata?.layer || data?.style?.layer || semanticCategory(data?.type);
  const shape = data?.style?.shape || shapeForType(data?.type);
  const color = data?.style?.color || CATEGORY_COLORS[category] || CATEGORY_COLORS.other;
  return (
    <div className={`semantic-rf-node semantic-rf-node--${shape} ${selected ? 'is-selected' : ''}`} style={{ '--node-accent': color }}>
      <Handle type="target" position={Position.Left} className="semantic-rf-handle" />
      <div className="semantic-rf-node__stripe" />
      <div className="semantic-rf-node__content">
        <span className="semantic-rf-node__icon" aria-hidden="true">{iconForShape(shape)}</span>
        <span className="semantic-rf-node__text">
          <strong title={data?.label}>{data?.label || data?.id}</strong>
          <small>{data?.type || 'Element'}</small>
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="semantic-rf-handle" />
    </div>
  );
});

function edgeStyleForType(type = '') {
  const value = String(type).toUpperCase();
  if (value.includes('COMPOSITION')) return { stroke: '#1f2933', strokeWidth: 1.8 };
  if (value.includes('AGGREGATION')) return { stroke: '#475569', strokeWidth: 1.5 };
  if (value.includes('SPECIALIZATION')) return { stroke: '#7c3aed', strokeWidth: 1.5, strokeDasharray: '6 4' };
  if (value.includes('REALIZATION')) return { stroke: '#005a9c', strokeWidth: 1.5, strokeDasharray: '6 4' };
  if (value.includes('FLOW') || value.includes('TRIGGER')) return { stroke: '#b45309', strokeWidth: 1.6 };
  if (value.includes('ACCESS')) return { stroke: '#be123c', strokeWidth: 1.4, strokeDasharray: '3 4' };
  if (value.includes('SERV') || value.includes('USED')) return { stroke: '#0f766e', strokeWidth: 1.5 };
  return { stroke: '#64748b', strokeWidth: 1.25 };
}

function sameSelectedState(node, selectedId) {
  return Boolean(node.selected) === Boolean(node.id === selectedId);
}

const NODE_TYPES = { semantic: SemanticNode };

export default function ReactFlowDiagramCanvas({
  graph = {},
  selectedId,
  onSelect,
  onGraphChange,
  onConnect,
  onNodeDoubleClick,
  diagramKind = 'archimate',
  viewportCommand,
}) {
   const flowInstanceRef = useRef(null);
  const lastViewportCommandRef = useRef(null);
  const rfNodesRef = useRef([]);
  const rfEdgesRef = useRef([]);
  const { nodes, edges } = useMemo(() => toReactFlowElements(graph), [graph]);

  const styledNodes = useMemo(() => nodes.map((node) => ({
    ...node,
    type: 'semantic',
    selected: node.id === selectedId,
    draggable: true,
  })), [nodes, selectedId]);

  const showEdgeLabels = edges.length <= 40;

  const styledEdges = useMemo(() => edges.map((edge) => {
    const style = edgeStyleForType(edge.data?.type || edge.label);
    return {
      ...edge,
      type: 'smoothstep',
      animated: false,
      label: showEdgeLabels ? (edge.data?.displayLabel || edge.label) : '',
      labelShowBg: showEdgeLabels,
      labelBgPadding: [5, 3],
      labelBgBorderRadius: 4,
      style,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: style.stroke },
    };
  }), [edges, showEdgeLabels]);

  const structureSignature = useMemo(() => JSON.stringify({
    nodes: styledNodes.map((node) => [node.id, Math.round(node.position?.x || 0), Math.round(node.position?.y || 0)]),
    edges: styledEdges.map((edge) => [edge.id, edge.source, edge.target, edge.label]),
  }), [styledNodes, styledEdges]);

  const [rfNodes, setRfNodes] = useState(styledNodes);
  const [rfEdges, setRfEdges] = useState(styledEdges);

  useEffect(() => { rfNodesRef.current = rfNodes; }, [rfNodes]);
  useEffect(() => { rfEdgesRef.current = rfEdges; }, [rfEdges]);

  useEffect(() => {
    setRfNodes(styledNodes);
    setRfEdges(styledEdges);
  }, [structureSignature, styledNodes, styledEdges]);

  useEffect(() => {
    setRfNodes((current) => current.map((node) => (
      sameSelectedState(node, selectedId)
        ? node
        : { ...node, selected: node.id === selectedId }
    )));
  }, [selectedId]);

  useEffect(() => {
    if (!flowInstanceRef.current || rfNodes.length === 0) return undefined;
    const timer = window.setTimeout(() => {
      flowInstanceRef.current?.fitView({ padding: 0.18, maxZoom: 1.15, duration: 220 });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [structureSignature, rfNodes.length]);

  useEffect(() => {
    if (!flowInstanceRef.current || !selectedId) return undefined;
    const selectedNode = rfNodesRef.current.find((node) => node.id === selectedId);
    if (!selectedNode) return undefined;
    const timer = window.setTimeout(() => {
      flowInstanceRef.current?.setCenter(
        (selectedNode.position?.x || 0) + ((selectedNode.width || 220) / 2),
        (selectedNode.position?.y || 0) + ((selectedNode.height || 84) / 2),
        { zoom: 1.05, duration: 240 }
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedId, structureSignature]);

  useEffect(() => {
    if (!viewportCommand || !flowInstanceRef.current || viewportCommand === lastViewportCommandRef.current) return;
    lastViewportCommandRef.current = viewportCommand;
    const command = String(viewportCommand).split(':')[0];
    if (command === 'zoom-in') flowInstanceRef.current.zoomIn({ duration: 180 });
    if (command === 'zoom-out') flowInstanceRef.current.zoomOut({ duration: 180 });
    if (command === 'fit') flowInstanceRef.current.fitView({ padding: 0.18, maxZoom: 1.15, duration: 220 });
  }, [viewportCommand]);

  const emitGraphChange = useCallback((nextNodes, nextEdges) => {
    onGraphChange?.(fromReactFlowElements(nextNodes, nextEdges));
  }, [onGraphChange]);

  const handleNodesChange = useCallback((changes) => {
    setRfNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const handleEdgesChange = useCallback((changes) => {
    setRfEdges((current) => {
      const nextEdges = applyEdgeChanges(changes, current);
      emitGraphChange(rfNodesRef.current, nextEdges);
      return nextEdges;
    });
  }, [emitGraphChange]);

  const handleConnect = useCallback((connection) => {
    const nextEdges = addEdge({ ...connection, type: 'smoothstep', label: 'TRACE_TO' }, rfEdgesRef.current);
    setRfEdges(nextEdges);
    onConnect?.(connection);
    emitGraphChange(rfNodesRef.current, nextEdges);
  }, [emitGraphChange, onConnect]);

  const handleNodeDragStop = useCallback(() => {
    emitGraphChange(rfNodesRef.current, rfEdgesRef.current);
  }, [emitGraphChange]);

  return (
    <div className={`react-flow-diagram-canvas react-flow-diagram-canvas--${diagramKind}`}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={NODE_TYPES}
        minZoom={0.18}
        maxZoom={2.2}
        defaultViewport={{ x: 0, y: 0, zoom: 0.9 }}
        nodesDraggable
        nodesConnectable
        elementsSelectable
        panOnDrag
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick={false}
        onInit={(instance) => { flowInstanceRef.current = instance; }}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeDragStop={handleNodeDragStop}
        onNodeClick={(_, node) => onSelect?.(node.data)}
        onNodeDoubleClick={(_, node) => onNodeDoubleClick?.(node.data)}
        onEdgeClick={(_, edge) => onSelect?.(edge.data)}
      >
        <Background gap={24} color="#d7e2ee" />
      </ReactFlow>
    </div>
  );
}






