import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Boxes, Network, GitFork, Layers, RefreshCcw, ZoomIn, ZoomOut, ScanSearch } from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import graphApi from '../services/graphApi';
import GraphVisualizationWidget from '../Components/GraphMiner/GraphVisualizationWidget';
import { createDiagramModel } from '../diagram/engine/diagramEngine';
import './ModelWorkbenchPage.css';

const VIEW_OPTIONS = [
  { id: 'architecture', label: 'ArchiMate', description: 'Imported architecture/process model diagrams.' },
  { id: 'mbse', label: 'MBSE / SysML / UML', description: 'Requirement, function, interface, part, and behavior diagram view.' },
];

function endpointId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value.elementId || value.uid || value.identity || '';
}

function cleanLabel(value, fallback = 'Unnamed') {
  const text = String(value || '').trim();
  return text || fallback;
}

function normalizeNode(raw) {
  const properties = raw?.properties && typeof raw.properties === 'object' ? raw.properties : {};
  const labels = Array.isArray(raw?.labels) ? raw.labels : [];
  const id = raw?.elementId || raw?.id || raw?.uid || raw?.identifier || properties.id || properties.uid || properties.identifier || properties.name;
  if (!id) return null;
  const type = raw?.type || raw?.subType || raw?.element_type || raw?.elementType || properties.type || properties.element_type || properties.elementType || labels[0] || 'Element';
  const label = cleanLabel(raw?.label || raw?.name || raw?.title || properties.label || properties.name || properties.title || properties.uid || id, String(id));
  return {
    id: String(id),
    label,
    type: cleanLabel(type, 'Element'),
    properties: { ...properties, ...Object.fromEntries(Object.entries(raw || {}).filter(([key]) => !['properties', 'labels'].includes(key))) },
  };
}

function normalizeLink(raw) {
  const properties = raw?.properties && typeof raw.properties === 'object' ? raw.properties : {};
  const source = endpointId(raw?.source || raw?.from || raw?.start);
  const target = endpointId(raw?.target || raw?.to || raw?.end);
  const id = raw?.id || raw?.elementId || raw?.uid || properties.id || `${source}-${raw?.type || raw?.label || 'REL'}-${target}`;
  if (!id || !source || !target) return null;
  return { id: String(id), source: String(source), target: String(target), type: cleanLabel(raw?.type || raw?.label || raw?.relationship_type || properties.type, 'RELATED_TO'), properties };
}

function normalizeDataset(payload) {
  const data = payload?.data || payload?.graph || payload || {};
  const rawNodes = data.nodes || data.vertices || [];
  const rawLinks = data.links || data.relationships || data.edges || [];
  const nodesById = new Map();
  rawNodes.forEach((item) => {
    const node = normalizeNode(item);
    if (node) nodesById.set(node.id, node);
  });
  const linksById = new Map();
  rawLinks.forEach((item) => {
    const link = normalizeLink(item);
    if (link && nodesById.has(link.source) && nodesById.has(link.target)) linksById.set(link.id, link);
  });
  return {
    nodes: Array.from(nodesById.values()).sort((a, b) => a.type.localeCompare(b.type) || a.label.localeCompare(b.label)),
    links: Array.from(linksById.values()).sort((a, b) => a.type.localeCompare(b.type)),
    message: data.message || payload?.message || '',
    representations: (data.representations || data.views || []).map((item) => ({
      id: String(item.id || item.identifier || item.name || ''),
      name: String(item.name || item.label || item.id || 'Diagram'),
      type: String(item.type || 'Diagram'),
      nodeIds: Array.isArray(item.nodeIds) ? item.nodeIds.map(String) : [],
      relationshipIds: Array.isArray(item.relationshipIds) ? item.relationshipIds.map(String) : [],
    })).filter((item) => item.id),
  };
}

function matchesQuery(node, query) {
  const q = String(query || '').trim().toLowerCase().replace(/\*/g, '');
  if (!q) return true;
  const searchable = [node.label, node.type, node.id, ...Object.values(node.properties || {}).map((v) => String(v || ''))].join(' ').toLowerCase();
  return searchable.includes(q);
}

function isContainerType(type = '') {
  return /package|folder|view|diagram/i.test(String(type));
}

function relationIsContainment(type = '') {
  return /CONTAINS|VIEW_CONTAINS|COMPOSITION|AGGREGATION/i.test(String(type));
}

function buildDescendantSet(rootId, links) {
  const descendants = new Set([rootId]);
  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift();
    links.forEach((link) => {
      if (relationIsContainment(link.type) && link.source === current && !descendants.has(link.target)) {
        descendants.add(link.target);
        queue.push(link.target);
      }
    });
  }
  return descendants;
}

function buildDecompositionSet(rootId, links) {
  const ids = buildDescendantSet(rootId, links);
  links.forEach((link) => {
    if (ids.has(link.source) || ids.has(link.target) || link.source === rootId || link.target === rootId) {
      ids.add(link.source);
      ids.add(link.target);
    }
  });
  return ids;
}

function buildOneHopContextSet(rootId, links) {
  const ids = new Set([rootId]);
  links.forEach((link) => {
    if (link.source === rootId) ids.add(link.target);
    if (link.target === rootId) ids.add(link.source);
  });
  return ids;
}

function buildContainmentAncestorSet(seedIds, links) {
  const initialIds = Array.isArray(seedIds)
    ? seedIds
    : seedIds
      ? [seedIds]
      : [];
  const ids = new Set(initialIds.map(String).filter(Boolean));
  const queue = Array.from(ids);
  while (queue.length > 0) {
    const current = queue.shift();
    links.forEach((link) => {
      if (relationIsContainment(link.type) && link.target === current && !ids.has(link.source)) {
        ids.add(link.source);
        queue.push(link.source);
      }
    });
  }
  return ids;
}

function isDecomposableElement(node) {
  return /(process|function|activity|capability|service|value|course|product|component|part|package|folder|view)/i.test(String(node?.type || node?.label || ''));
}

function representationNodeIds(representation, links) {
  const initialIds = Array.isArray(representation?.nodeIds)
    ? representation.nodeIds
    : representation?.nodeIds
      ? [representation.nodeIds]
      : [];
  const ids = new Set(initialIds.map(String));
  const viewId = String(representation?.id || '');
  if (viewId) {
    links.forEach((link) => {
      if (link.source === viewId && /VIEW_CONTAINS|CONTAINS/i.test(link.type)) ids.add(link.target);
    });
  }
  return ids;
}

function getModelName(dataset, activeView) {
  const first = dataset.nodes[0]?.properties || {};
  return first.model_name || first.source_filename || (activeView === 'architecture' ? 'ArchiMate model' : 'MBSE model');
}

function scopedNodeIds(children = []) {
  const ids = new Set();
  children.forEach((child) => {
    (child.nodeIds || [child.nodeId]).filter(Boolean).forEach((id) => ids.add(id));
  });
  return Array.from(ids);
}

function makeTreeNode(node, children = []) {
  const nodeIds = new Set([node.id]);
  scopedNodeIds(children).forEach((id) => nodeIds.add(id));
  return { id: node.id, label: node.label, type: node.type, nodeId: node.id, nodeIds: Array.from(nodeIds), children };
}

function makeTreeGroup(id, label, type, children = []) {
  return { id, label, type, nodeIds: scopedNodeIds(children), children };
}

function buildModelTree(dataset, activeView) {
  const nodeMap = new Map(dataset.nodes.map((node) => [node.id, node]));
  const childIds = new Set();
  const packageChildren = new Map();
  dataset.links.forEach((link) => {
    if (!relationIsContainment(link.type)) return;
    const source = nodeMap.get(link.source);
    const target = nodeMap.get(link.target);
    if (!source || !target || !isContainerType(source.type)) return;
    if (!packageChildren.has(source.id)) packageChildren.set(source.id, []);
    packageChildren.get(source.id).push(target.id);
    childIds.add(target.id);
  });

  const renderPackage = (nodeId, visited = new Set()) => {
    if (visited.has(nodeId)) return null;
    const node = nodeMap.get(nodeId);
    if (!node) return null;
    const nextVisited = new Set([...visited, nodeId]);
    const children = (packageChildren.get(nodeId) || [])
      .map((childId) => renderPackage(childId, nextVisited) || makeTreeNode(nodeMap.get(childId), []))
      .filter(Boolean)
      .sort((a, b) => a.label.localeCompare(b.label));
    return makeTreeNode(node, children);
  };

  const packageRoots = dataset.nodes
    .filter((node) => isContainerType(node.type) && !childIds.has(node.id))
    .map((node) => renderPackage(node.id))
    .filter(Boolean)
    .sort((a, b) => a.label.localeCompare(b.label));

  const decompositionChildren = new Map();
  const decompositionChildIds = new Set();
  dataset.links.forEach((link) => {
    if (!/COMPOSITION|AGGREGATION/i.test(link.type)) return;
    const source = nodeMap.get(link.source);
    const target = nodeMap.get(link.target);
    if (!source || !target) return;
    if (!decompositionChildren.has(source.id)) decompositionChildren.set(source.id, []);
    decompositionChildren.get(source.id).push(target.id);
    decompositionChildIds.add(target.id);
  });

  const renderDecomposition = (nodeId, visited = new Set()) => {
    if (visited.has(nodeId)) return null;
    const node = nodeMap.get(nodeId);
    if (!node) return null;
    const nextVisited = new Set([...visited, nodeId]);
    const children = (decompositionChildren.get(nodeId) || [])
      .map((childId) => renderDecomposition(childId, nextVisited) || makeTreeNode(nodeMap.get(childId), []))
      .filter(Boolean)
      .sort((a, b) => a.label.localeCompare(b.label));
    return makeTreeNode(node, children);
  };

  const decompositionRoots = dataset.nodes
    .filter((node) => decompositionChildren.has(node.id) && !decompositionChildIds.has(node.id))
    .map((node) => renderDecomposition(node.id))
    .filter(Boolean)
    .sort((a, b) => a.label.localeCompare(b.label));
  const representationNodes = (dataset.representations || []).map((view) => ({
    id: `view:${view.id}`,
    label: view.name,
    type: view.type || 'Diagram',
    representationId: view.id,
    children: [],
    nodeIds: Array.from(representationNodeIds(view, dataset.links)),
  }));

  const elementGroups = [];
  if (packageRoots.length === 0) {
    const grouped = new Map();
    dataset.nodes.filter((node) => !isContainerType(node.type)).forEach((node) => {
      const key = node.type || 'Element';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(node);
    });
    grouped.forEach((items, type) => {
      elementGroups.push({
        id: `type:${type}`,
        label: type,
        type: 'Element Group',
        nodeIds: items.map((node) => node.id),
        children: items
          .sort((a, b) => a.label.localeCompare(b.label))
          .slice(0, 300)
          .map((node) => makeTreeNode(node, [])),
      });
    });
    elementGroups.sort((a, b) => a.label.localeCompare(b.label));
  }

  const rootChildren = [
    ...(representationNodes.length ? [makeTreeGroup('root:views', 'Views', 'Folder', representationNodes)] : []),
    ...(packageRoots.length ? [makeTreeGroup('root:packages', 'Model', 'Folder', packageRoots)] : []),
    ...(decompositionRoots.length ? [makeTreeGroup('root:decomposition', 'Decomposition', 'Folder', decompositionRoots)] : []),
    ...(elementGroups.length ? [makeTreeGroup('root:elements', 'Elements', 'Folder', elementGroups)] : []),
  ];
  return [makeTreeGroup('root:model', getModelName(dataset, activeView), activeView === 'architecture' ? 'ArchiMate Model' : 'Model', rootChildren)];
}

function treeContainsSelection(item, selectedId) {
  if (!item || !selectedId) return false;
  if (item.id === selectedId || item.nodeId === selectedId || item.representationId === selectedId) return true;
  return Array.isArray(item.children) && item.children.some((child) => treeContainsSelection(child, selectedId));
}

function TreeBranch({ item, selectedId, onSelect, depth = 0 }) {
  const hasChildren = Array.isArray(item.children) && item.children.length > 0;
  const shouldAutoOpen = hasChildren && treeContainsSelection(item, selectedId);
  const [open, setOpen] = useState(depth < 2 || shouldAutoOpen);

  useEffect(() => {
    if (shouldAutoOpen) setOpen(true);
  }, [shouldAutoOpen]);
  return (
    <div className="archi-tree-row-wrap">
      <button
        type="button"
        className={`archi-tree-row ${selectedId === item.id || selectedId === item.nodeId || selectedId === item.representationId ? 'selected' : ''}`}
        style={{ paddingLeft: `${10 + depth * 16}px` }}
        onClick={() => {
          if (hasChildren) setOpen((current) => !current);
          onSelect?.(item);
        }}
      >
        <span className="archi-tree-caret">{hasChildren ? (open ? 'v' : '>') : ''}</span>
        <span className="archi-tree-icon">{hasChildren || isContainerType(item.type) ? '[]' : '-'}</span>
        <span className="archi-tree-label"><strong>{item.label}</strong><small>{item.type}</small></span>
      </button>
      {open && hasChildren && <div>{item.children.map((child) => <TreeBranch key={child.id} item={child} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />)}</div>}
    </div>
  );
}

export default function ModelWorkbenchPage({ onNavigate }) {
  const [activeView, setActiveView] = useState('architecture');
  const [query, setQuery] = useState('');
  const [dataset, setDataset] = useState({ nodes: [], links: [], message: '', representations: [] });
  const [selectedId, setSelectedId] = useState('');
  const [activeTreeItem, setActiveTreeItem] = useState(null);
  const [activeRepresentationId, setActiveRepresentationId] = useState('');
  const [decompositionRootId, setDecompositionRootId] = useState('');
  const [status, setStatus] = useState({ loading: false, error: '' });
  const [reactFlowGraph, setReactFlowGraph] = useState(null);
  const [viewportCommand, setViewportCommand] = useState('');
  const loadRequestIdRef = useRef(0);
  const loadAbortControllerRef = useRef(null);

  const loadView = useCallback(async () => {
    const requestId = ++loadRequestIdRef.current;
    loadAbortControllerRef.current?.abort();
    const controller = new AbortController();
    loadAbortControllerRef.current = controller;
    setStatus({ loading: true, error: '' });
    try {
      const response = activeView === 'architecture'
        ? await graphApi.getArchitectureGraph('archimate', 1800, controller.signal)
        : await API_METHODS.modeling.graph({ limit: 1600 }, controller.signal);
      if (requestId !== loadRequestIdRef.current) return;
      const normalized = normalizeDataset(response?.data);
      setDataset(normalized);
      setSelectedId('');
      setActiveTreeItem(null);
      setActiveRepresentationId(normalized.representations?.[0]?.id || '');
      setDecompositionRootId('');
      setReactFlowGraph(null);
      setStatus({ loading: false, error: '' });
    } catch (err) {
      if (requestId !== loadRequestIdRef.current || controller.signal.aborted) return;
      setDataset({ nodes: [], links: [], message: '', representations: [] });
      setSelectedId('');
      setActiveTreeItem(null);
      setActiveRepresentationId('');
      setDecompositionRootId('');
      setReactFlowGraph(null);
      setStatus({ loading: false, error: err?.response?.data?.detail || err?.message || 'Unable to load model viewer data.' });
    }
  }, [activeView]);

  useEffect(() => { loadView(); }, [loadView]);
  useEffect(() => () => {
    loadRequestIdRef.current += 1;
    loadAbortControllerRef.current?.abort();
  }, []);

  const modelTree = useMemo(() => buildModelTree(dataset, activeView), [dataset, activeView]);
  const matchedNodes = useMemo(() => dataset.nodes.filter((node) => matchesQuery(node, query)), [dataset.nodes, query]);
  const activeRepresentation = useMemo(() => (dataset.representations || []).find((item) => item.id === activeRepresentationId) || null, [dataset.representations, activeRepresentationId]);

  const selectedElement = useMemo(() => dataset.nodes.find((node) => node.id === selectedId) || null, [dataset.nodes, selectedId]);

  const visibleNodes = useMemo(() => {
    const ids = new Set();
    if (query.trim()) {
      matchedNodes.forEach((node) => ids.add(node.id));
    } else if (decompositionRootId) {
      buildDecompositionSet(decompositionRootId, dataset.links).forEach((id) => ids.add(id));
    } else if (activeTreeItem?.representationId && activeRepresentation) {
      buildContainmentAncestorSet(representationNodeIds(activeRepresentation, dataset.links), dataset.links).forEach((id) => ids.add(id));
    } else if (activeTreeItem?.nodeId && !isContainerType(activeTreeItem.type)) {
      buildOneHopContextSet(activeTreeItem.nodeId, dataset.links).forEach((id) => ids.add(id));
    } else if (activeTreeItem?.nodeIds?.length) {
      activeTreeItem.nodeIds.forEach((id) => ids.add(id));
    } else if (activeTreeItem?.nodeId) {
      buildDecompositionSet(activeTreeItem.nodeId, dataset.links).forEach((id) => ids.add(id));
      dataset.links.forEach((link) => {
        if (relationIsContainment(link.type) && ids.has(link.source)) {
          ids.add(link.target);
        }
      });
    } else if (activeRepresentation) {
      representationNodeIds(activeRepresentation, dataset.links).forEach((id) => ids.add(id));
    }
    if (ids.size === 0) dataset.nodes.filter((node) => !isContainerType(node.type)).slice(0, 160).forEach((node) => ids.add(node.id));
    return dataset.nodes.filter((node) => ids.has(node.id) && !(/^id\d+$/i.test(node.label) && !query.trim()));
  }, [activeRepresentation, activeTreeItem, dataset.links, dataset.nodes, decompositionRootId, matchedNodes, query]);

  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const visibleLinks = useMemo(() => dataset.links.filter((link) => visibleIds.has(link.source) && visibleIds.has(link.target) && !/VIEW_CONTAINS/i.test(link.type)), [dataset.links, visibleIds]);
  const selectedRelationships = useMemo(() => {
    if (!selectedElement) return [];
    return visibleLinks
      .filter((link) => link.source === selectedElement.id || link.target === selectedElement.id)
      .slice(0, 12)
      .map((link) => ({
        id: link.id,
        type: link.type,
        direction: link.source === selectedElement.id ? 'outgoing' : 'incoming',
        otherId: link.source === selectedElement.id ? link.target : link.source,
      }));
  }, [selectedElement, visibleLinks]);
  const selectedRelationshipTargets = useMemo(() => {
    const byId = new Map(dataset.nodes.map((node) => [node.id, node]));
    return selectedRelationships.map((link) => ({
      ...link,
      otherNode: byId.get(link.otherId) || null,
    }));
  }, [dataset.nodes, selectedRelationships]);
  const engineDiagram = useMemo(() => createDiagramModel({ nodes: visibleNodes, links: visibleLinks }, activeView === 'architecture' ? 'archimate' : 'uaf'), [activeView, visibleNodes, visibleLinks]);

  useEffect(() => { setReactFlowGraph(engineDiagram.graph); }, [engineDiagram]);

  const activeCanvasGraph = reactFlowGraph || engineDiagram.graph;
  const validation = useMemo(() => {
    const issues = [];
    const ids = new Set(dataset.nodes.map((node) => node.id));
    dataset.links.forEach((link) => { if (!ids.has(link.source) || !ids.has(link.target)) issues.push(`Broken endpoint: ${link.type}`); });
    dataset.nodes.forEach((node) => { if (!node.label || node.label === node.id) issues.push(`Missing business label: ${node.id}`); });
    return issues.slice(0, 8);
  }, [dataset]);

  const handleTreeSelect = useCallback((item) => {
    setActiveTreeItem(item);
    setSelectedId(item?.nodeId || '');
    setDecompositionRootId('');
    setQuery('');
    if (item?.representationId) {
      setActiveRepresentationId(item.representationId);
      return;
    }
    if (item?.type && /ArchiMate Model|Model|Folder|Element Group/i.test(item.type) && !item?.nodeId) {
      return;
    }
    setActiveRepresentationId('');
  }, []);

  const handleCanvasDoubleClick = useCallback((item) => {
    if (!item?.id) return;
    setSelectedId(item.id);
    if (!isDecomposableElement(item)) return;
    setQuery('');
    setActiveRepresentationId('');
    setDecompositionRootId(item.id);
    setActiveTreeItem({ id: `decomposition:${item.id}`, label: item.label || item.id, type: `${item.type || 'Element'} decomposition`, nodeId: item.id });
  }, []);

  return (
    <div className="model-viewer-page">
      <header className="model-viewer-header compact-header">
        <div className="model-viewer-header-main">
          <h1><Layers size={22} /> Modeling Viewer</h1>
          <p>Semantic ArchiMate / MBSE diagram viewer with model tree, drag, pan, and zoom.</p>
          <div className="model-viewer-tabs compact-header-tabs" role="tablist" aria-label="Model viewer modes">
            {VIEW_OPTIONS.map((view) => <button key={view.id} type="button" className={activeView === view.id ? 'active' : ''} onClick={() => { setActiveView(view.id); setQuery(''); setSelectedId(''); setActiveTreeItem(null); setActiveRepresentationId(''); }}>{view.label}</button>)}
          </div>
        </div>
        <div className="model-viewer-actions">
          <button type="button" onClick={loadView} disabled={status.loading}><RefreshCcw size={15} /> Refresh</button>
          <button type="button" onClick={() => onNavigate?.('graph')}><GitFork size={15} /> Graph Explorer</button>
        </div>
      </header>


      <section className="model-viewer-inspector-bar">
        <div><strong>{getModelName(dataset, activeView)}</strong><span>{decompositionRootId ? `Decomposition: ${selectedElement?.label || decompositionRootId}` : activeTreeItem?.label || activeRepresentation?.name || 'Overview'}</span></div>
        <div><strong>{visibleNodes.length}</strong><span>Visible elements</span></div>
        <div><strong>{visibleLinks.length}</strong><span>Visible relationships</span></div>
        <div><strong>{query.trim() ? matchedNodes.length : dataset.nodes.length}</strong><span>{query.trim() ? 'Matches' : 'Model elements'}</span></div>
        <div><strong>{validation.length}</strong><span>Checks</span></div>
        {selectedElement && <div className="selected-inline"><strong>{selectedElement.label}</strong><span>{selectedElement.type}</span></div>}
      </section>

      {status.error && <div className="model-viewer-error"><AlertTriangle size={16} /> {status.error}</div>}
      {!status.error && dataset.message && <div className="model-viewer-note">{dataset.message}</div>}

      <main className="model-viewer-layout tree-diagram semantic-viewer-layout">
        <section className="model-viewer-panel model-viewer-elements archi-model-tree-panel">
          <div className="panel-title"><Boxes size={16} /> Model Tree</div>
          <div className="archi-model-tree">
            {modelTree.map((item) => <TreeBranch key={item.id} item={item} selectedId={activeTreeItem?.id || selectedId || activeRepresentationId} onSelect={handleTreeSelect} />)}
            {dataset.nodes.length === 0 && <div className="empty-state">No model loaded.</div>}
          </div>
        </section>

        <section className="model-viewer-panel model-diagram-panel semantic-diagram-panel">
          <div className="panel-title model-diagram-header"><span className="model-diagram-title"><Network size={16} /> Diagram Canvas <span className="diagram-count">{`${visibleNodes.length} elements / ${visibleLinks.length} relationships`}</span></span><span className="model-diagram-controls"><button type="button" className="canvas-control-button" onClick={() => setViewportCommand(`zoom-out:${Date.now()}`)} aria-label="Zoom out"><ZoomOut size={14} /></button><button type="button" className="canvas-control-button" onClick={() => setViewportCommand(`zoom-in:${Date.now()}`)} aria-label="Zoom in"><ZoomIn size={14} /></button><button type="button" className="canvas-control-button" onClick={() => setViewportCommand(`fit:${Date.now()}`)} aria-label="Fit diagram"><ScanSearch size={14} /></button></span></div>
          <div className="semantic-canvas-wrap react-flow-wrap">
            {(activeCanvasGraph.nodes || []).length === 0 ? <div className="empty-state">No diagram elements available. Select a view/folder or clear the search filter.</div> : <GraphVisualizationWidget renderer="react-flow" graph={activeCanvasGraph} diagramKind={activeView === 'architecture' ? 'archimate' : 'uaf'} selectedId={selectedElement?.id} viewportCommand={viewportCommand} onSelect={(item) => { if (item?.id) setSelectedId(item.id); }} onGraphChange={setReactFlowGraph} onNodeDoubleClick={handleCanvasDoubleClick} />}
          </div>
        </section>

        <aside className="model-viewer-panel model-viewer-inspector-panel">
          <div className="panel-title"><AlertTriangle size={16} /> Inspector</div>
          {selectedElement ? (
            <>
              <div className="selected-card">
                <span className="type-dot large" style={{ background: '#005a9c' }} />
                <div>
                  <strong>{selectedElement.label}</strong>
                  <small>{selectedElement.type}</small>
                </div>
              </div>
              <div className="context-list">
                <strong>Context</strong>
                <span>{`ID: ${selectedElement.id}`}</span>
                <span>{`${selectedRelationshipTargets.length} connected relationships`}</span>
                {decompositionRootId === selectedElement.id && <span>Active decomposition root</span>}
              </div>
              <div className="property-list">
                {Object.entries(selectedElement.properties || {}).slice(0, 24).map(([key, value]) => (
                  <div key={key}>
                    <span>{key}</span>
                    <strong>{String(value ?? '') || '-'}</strong>
                  </div>
                ))}
                {Object.keys(selectedElement.properties || {}).length === 0 && <div><span>Properties</span><strong>-</strong></div>}
              </div>
              <div className="validation-list">
                <strong>Relationships</strong>
                {selectedRelationshipTargets.length > 0 ? selectedRelationshipTargets.map((link) => (
                  <span key={link.id}>
                    {`${link.direction === 'outgoing' ? '->' : '<-'} ${link.type} ${link.otherNode?.label || link.otherId}`}
                  </span>
                )) : <span>No visible relationships in current canvas scope.</span>}
              </div>
            </>
          ) : (
            <div className="empty-state">Select a model tree item or diagram element to inspect its properties and connected relationships.</div>
          )}
          <div className="validation-list">
            <strong>Validation</strong>
            {validation.length > 0 ? validation.map((issue) => <span key={issue}>{issue}</span>) : <span className="valid">No viewer-level issues found.</span>}
          </div>
        </aside>
      </main>
    </div>
  );
}




















