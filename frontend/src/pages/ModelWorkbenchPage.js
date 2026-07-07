import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Boxes, GitFork, Layers, RefreshCcw, Search } from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import graphApi from '../services/graphApi';
import './ModelWorkbenchPage.css';

const VIEW_OPTIONS = [
  { id: 'architecture', label: 'ArchiMate', description: 'Layered architecture/process model diagram.' },
  { id: 'mbse', label: 'MBSE / SysML / UML', description: 'Requirement, function, interface, part, and behavior diagram view.' },
];

const LAYERS = [
  { id: 'motivation', label: 'Motivation / Requirements', color: '#b45309' },
  { id: 'strategy', label: 'Strategy / Capability', color: '#7c3aed' },
  { id: 'business', label: 'Business / Operational', color: '#0f766e' },
  { id: 'application', label: 'Application / Functional', color: '#005a9c' },
  { id: 'technology', label: 'Technology / Physical', color: '#166534' },
  { id: 'implementation', label: 'Implementation / Product', color: '#334155' },
  { id: 'other', label: 'Other', color: '#64748b' },
];

const TYPE_COLORS = {
  Requirement: '#b45309', Constraint: '#b45309', Goal: '#b45309', Principle: '#b45309', Driver: '#b45309', Assessment: '#b45309',
  Capability: '#7c3aed', CourseOfAction: '#7c3aed', Resource: '#7c3aed', ValueStream: '#7c3aed',
  BusinessActor: '#0f766e', BusinessRole: '#0f766e', BusinessProcess: '#0f766e', BusinessFunction: '#0f766e', BusinessObject: '#0f766e', OperationalActivity: '#0f766e', Performer: '#0f766e',
  ApplicationComponent: '#005a9c', ApplicationService: '#005a9c', DataObject: '#005a9c', Function: '#005a9c', UseCase: '#005a9c', Activity: '#005a9c', Interface: '#be123c',
  Node: '#166534', Device: '#166534', SystemSoftware: '#166534', TechnologyService: '#166534', Artifact: '#166534', Part: '#166534', Component: '#166534', Block: '#166534',
  Product: '#334155', WorkPackage: '#334155', Deliverable: '#334155', Document: '#6b7280', Package: '#64748b',
};

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
  const id = raw?.id || raw?.elementId || raw?.uid || raw?.identifier || properties.id || properties.uid || properties.identifier || properties.name;
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
  const id = raw?.id || raw?.elementId || raw?.uid || properties.id || `${endpointId(raw?.source)}-${raw?.type || raw?.label || 'REL'}-${endpointId(raw?.target)}`;
  const source = endpointId(raw?.source || raw?.from || raw?.start);
  const target = endpointId(raw?.target || raw?.to || raw?.end);
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
      name: String(item.name || item.label || item.id || 'Representation'),
      type: String(item.type || 'Representation'),
      nodeIds: Array.isArray(item.nodeIds) ? item.nodeIds.map(String) : [],
      relationshipIds: Array.isArray(item.relationshipIds) ? item.relationshipIds.map(String) : [],
    })).filter((item) => item.id),
  };
}

function layerForType(type = '') {
  const value = String(type).toLowerCase();
  if (/(requirement|constraint|goal|principle|driver|assessment|stakeholder)/.test(value)) return 'motivation';
  if (/(capability|courseofaction|resource|valuestream|strategy)/.test(value)) return 'strategy';
  if (/(business|operational|actor|role|performer|process)/.test(value)) return 'business';
  if (/(application|function|usecase|activity|interface|dataobject|logical)/.test(value)) return 'application';
  if (/(technology|device|node|software|artifact|part|block|component|physical)/.test(value)) return 'technology';
  if (/(product|workpackage|deliverable|document|implementation|migration)/.test(value)) return 'implementation';
  return 'other';
}

function matchesQuery(node, query) {
  if (!query) return true;
  const q = query.toLowerCase().replace('*', '');
  const searchable = [node.label, node.type, node.id, ...Object.values(node.properties || {}).map((v) => String(v || ''))].join(' ').toLowerCase();
  return searchable.includes(q);
}

function applyNodePositions(diagram, positions) {
  const nodeMap = new Map();
  const nodes = diagram.nodes.map((node) => {
    const override = positions[node.id];
    const positioned = override ? { ...node, x: override.x, y: override.y } : node;
    nodeMap.set(positioned.id, positioned);
    return positioned;
  });
  return { ...diagram, nodes, nodeMap };
}

function buildDiagram(nodes, links) {
  const maxNodes = 140;
  const shownNodes = nodes.slice(0, maxNodes);
  const visible = new Set(shownNodes.map((node) => node.id));
  const shownLinks = links.filter((link) => visible.has(link.source) && visible.has(link.target)).slice(0, 260);
  const degree = new Map(shownNodes.map((node) => [node.id, 0]));
  shownLinks.forEach((link) => {
    degree.set(link.source, (degree.get(link.source) || 0) + 1);
    degree.set(link.target, (degree.get(link.target) || 0) + 1);
  });

  const orderedNodes = [...shownNodes].sort((a, b) => {
    const degreeDiff = (degree.get(b.id) || 0) - (degree.get(a.id) || 0);
    if (degreeDiff !== 0) return degreeDiff;
    const layerDiff = LAYERS.findIndex((layer) => layer.id === layerForType(a.type)) - LAYERS.findIndex((layer) => layer.id === layerForType(b.type));
    if (layerDiff !== 0) return layerDiff;
    return a.label.localeCompare(b.label);
  });

  const nodeWidth = 190;
  const nodeHeight = 62;
  const columnGap = 78;
  const rowGap = 52;
  const columns = Math.max(3, Math.min(5, Math.ceil(Math.sqrt(Math.max(orderedNodes.length, 1)))));
  const positioned = new Map();
  orderedNodes.forEach((node, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const layerOffset = (LAYERS.findIndex((layer) => layer.id === layerForType(node.type)) % 3) * 18;
    positioned.set(node.id, {
      ...node,
      x: 76 + column * (nodeWidth + columnGap) + (row % 2) * 34,
      y: 82 + row * (nodeHeight + rowGap) + layerOffset,
      width: nodeWidth,
      height: nodeHeight,
      layer: layerForType(node.type),
    });
  });
  const rows = Math.max(1, Math.ceil(orderedNodes.length / columns));
  return {
    nodes: Array.from(positioned.values()),
    links: shownLinks,
    nodeMap: positioned,
    width: Math.max(980, 150 + columns * (nodeWidth + columnGap)),
    height: Math.max(620, 170 + rows * (nodeHeight + rowGap)),
    truncated: nodes.length > maxNodes,
  };
}

export default function ModelWorkbenchPage({ onNavigate }) {
  const [activeView, setActiveView] = useState('architecture');
  const [query, setQuery] = useState('');
  const [dataset, setDataset] = useState({ nodes: [], links: [], message: '' });
  const [selectedId, setSelectedId] = useState('');
  const [treeScope, setTreeScope] = useState(null);
  const [activeRepresentationId, setActiveRepresentationId] = useState('');
  const [canvasTransform, setCanvasTransform] = useState({ x: 0, y: 0, k: 1 });
  const [nodePositions, setNodePositions] = useState({});
  const svgRef = useRef(null);
  const interactionRef = useRef(null);
  const [status, setStatus] = useState({ loading: false, error: '' });

  const loadView = useCallback(async () => {
    setStatus({ loading: true, error: '' });
    try {
      const response = activeView === 'architecture'
        ? await graphApi.getArchitectureGraph('archimate', 1600)
        : await API_METHODS.modeling.graph({ limit: 1600 });
      const normalized = normalizeDataset(response?.data);
      setDataset(normalized);
      setSelectedId((current) => (current && normalized.nodes.some((node) => node.id === current) ? current : ''));
      setTreeScope(null);
      setActiveRepresentationId(normalized.representations?.[0]?.id || '');
      setNodePositions({});
      setCanvasTransform({ x: 0, y: 0, k: 1 });
      setStatus({ loading: false, error: '' });
    } catch (err) {
      setDataset({ nodes: [], links: [], message: '' });
      setSelectedId('');
      setTreeScope(null);
      setActiveRepresentationId('');
      setNodePositions({});
      setCanvasTransform({ x: 0, y: 0, k: 1 });
      setStatus({ loading: false, error: err?.response?.data?.detail || err?.message || 'Unable to load model viewer data.' });
    }
  }, [activeView]);

  useEffect(() => { loadView(); }, [loadView]);

  const matchedNodes = useMemo(() => dataset.nodes.filter((node) => matchesQuery(node, query)), [dataset.nodes, query]);
  const visibleNodes = useMemo(() => {
    if (!query.trim()) return dataset.nodes;
    const ids = new Set(matchedNodes.map((node) => node.id));
    dataset.links.forEach((link) => {
      if (ids.has(link.source) || ids.has(link.target)) {
        ids.add(link.source);
        ids.add(link.target);
      }
    });
    return dataset.nodes.filter((node) => ids.has(node.id));
  }, [dataset.nodes, dataset.links, matchedNodes, query]);
  const matchedIds = useMemo(() => new Set(matchedNodes.map((node) => node.id)), [matchedNodes]);
  const activeRepresentation = useMemo(() => (dataset.representations || []).find((item) => item.id === activeRepresentationId) || null, [dataset.representations, activeRepresentationId]);
  const representationBaseNodes = useMemo(() => {
    if (!activeRepresentation) return visibleNodes;
    const ids = new Set(activeRepresentation.nodeIds || []);
    return visibleNodes.filter((node) => ids.has(node.id));
  }, [activeRepresentation, visibleNodes]);
  const selectedNode = useMemo(() => dataset.nodes.find((node) => node.id === selectedId) || null, [dataset.nodes, selectedId]);
  const scopedNodes = useMemo(() => {
    if (!treeScope) return representationBaseNodes;
    return representationBaseNodes.filter((node) => {
      const nodeLayer = layerForType(node.type);
      if (treeScope.kind === 'layer') return nodeLayer === treeScope.layer;
      if (treeScope.kind === 'type') return nodeLayer === treeScope.layer && node.type === treeScope.type;
      return true;
    });
  }, [treeScope, representationBaseNodes]);
  const representationNodes = useMemo(() => {
    if (!selectedNode) return scopedNodes;
    const ids = new Set([selectedNode.id]);
    dataset.links.forEach((link) => {
      if (link.source === selectedNode.id || link.target === selectedNode.id) {
        ids.add(link.source);
        ids.add(link.target);
      }
    });
    return dataset.nodes.filter((node) => ids.has(node.id));
  }, [dataset.nodes, dataset.links, selectedNode, scopedNodes]);
  const representationIds = useMemo(() => new Set(representationNodes.map((node) => node.id)), [representationNodes]);
  const representationLinks = useMemo(() => dataset.links.filter((link) => representationIds.has(link.source) && representationIds.has(link.target)), [dataset.links, representationIds]);
  const diagram = useMemo(() => applyNodePositions(buildDiagram(representationNodes, representationLinks), nodePositions), [representationNodes, representationLinks, nodePositions]);
  const modelInfo = useMemo(() => {
    const first = dataset.nodes[0]?.properties || {};
    const typeCounts = new Map();
    dataset.nodes.forEach((node) => typeCounts.set(node.type, (typeCounts.get(node.type) || 0) + 1));
    return {
      name: first.model_name || first.source_filename || 'Imported model',
      source: first.source_filename || first.source_ontology || activeView,
      types: Array.from(typeCounts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 4),
    };
  }, [dataset.nodes, activeView]);
  const representationTitle = useMemo(() => {
    if (selectedNode) return selectedNode.label;
    if (treeScope?.kind === 'type') return treeScope.type;
    if (treeScope?.kind === 'layer') return LAYERS.find((layer) => layer.id === treeScope.layer)?.label || 'Scoped model view';
    if (activeRepresentation) return activeRepresentation.name;
    return modelInfo.name;
  }, [activeRepresentation, modelInfo.name, selectedNode, treeScope]);
  const representationSubtitle = useMemo(() => {
    if (selectedNode) return `${selectedNode.type} one-hop representation`;
    if (treeScope?.kind === 'type') return 'Type-level representation';
    if (treeScope?.kind === 'layer') return 'Layer-level representation';
    if (activeRepresentation) return activeRepresentation.type || 'Imported representation';
    return modelInfo.source;
  }, [activeRepresentation, modelInfo.source, selectedNode, treeScope]);
  const treeGroups = useMemo(() => LAYERS.map((layer) => {
    const nodes = visibleNodes.filter((node) => layerForType(node.type) === layer.id);
    const typeMap = new Map();
    nodes.forEach((node) => {
      const key = node.type || 'Element';
      if (!typeMap.has(key)) typeMap.set(key, []);
      typeMap.get(key).push(node);
    });
    return {
      ...layer,
      count: nodes.length,
      types: Array.from(typeMap.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([type, items]) => ({
          type,
          count: items.length,
          nodes: items.slice(0, 18),
        })),
    };
  }).filter((group) => group.count > 0), [visibleNodes]);
  const validation = useMemo(() => {
    const issues = [];
    const ids = new Set(dataset.nodes.map((node) => node.id));
    dataset.links.forEach((link) => { if (!ids.has(link.source) || !ids.has(link.target)) issues.push(`Broken endpoint: ${link.type}`); });
    dataset.nodes.forEach((node) => { if (!node.label || node.label === node.id) issues.push(`Missing business label: ${node.id}`); });
    return issues.slice(0, 8);
  }, [dataset]);

  useEffect(() => {
    setNodePositions({});
    setCanvasTransform({ x: 0, y: 0, k: 1 });
  }, [activeView, activeRepresentationId]);

  const svgPoint = useCallback((event) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0, rawX: 0, rawY: 0 };
    const rect = svg.getBoundingClientRect();
    const rawX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * diagram.width;
    const rawY = ((event.clientY - rect.top) / Math.max(1, rect.height)) * diagram.height;
    return {
      x: (rawX - canvasTransform.x) / canvasTransform.k,
      y: (rawY - canvasTransform.y) / canvasTransform.k,
      rawX,
      rawY,
    };
  }, [canvasTransform, diagram.height, diagram.width]);

  const handleCanvasWheel = useCallback((event) => {
    event.preventDefault();
    const point = svgPoint(event);
    const nextScale = Math.max(0.35, Math.min(2.8, canvasTransform.k * (event.deltaY < 0 ? 1.12 : 0.88)));
    setCanvasTransform({
      k: nextScale,
      x: point.rawX - point.x * nextScale,
      y: point.rawY - point.y * nextScale,
    });
  }, [canvasTransform.k, svgPoint]);

  const handleCanvasPointerDown = useCallback((event) => {
    if (event.button !== 0) return;
    const point = svgPoint(event);
    interactionRef.current = { type: 'pan', rawX: point.rawX, rawY: point.rawY, startX: canvasTransform.x, startY: canvasTransform.y };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }, [canvasTransform.x, canvasTransform.y, svgPoint]);

  const handleNodePointerDown = useCallback((event, node) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    const point = svgPoint(event);
    interactionRef.current = { type: 'node', id: node.id, offsetX: point.x - node.x, offsetY: point.y - node.y };
    setTreeScope(null);
    setSelectedId(node.id);
    event.currentTarget.ownerSVGElement?.setPointerCapture?.(event.pointerId);
  }, [svgPoint]);

  const handleCanvasPointerMove = useCallback((event) => {
    const interaction = interactionRef.current;
    if (!interaction) return;
    const point = svgPoint(event);
    if (interaction.type === 'pan') {
      setCanvasTransform((current) => ({ ...current, x: interaction.startX + point.rawX - interaction.rawX, y: interaction.startY + point.rawY - interaction.rawY }));
      return;
    }
    if (interaction.type === 'node') {
      setNodePositions((current) => ({ ...current, [interaction.id]: { x: point.x - interaction.offsetX, y: point.y - interaction.offsetY } }));
    }
  }, [svgPoint]);

  const stopCanvasInteraction = useCallback((event) => {
    interactionRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }, []);

  const resetCanvasView = useCallback(() => {
    setCanvasTransform({ x: 0, y: 0, k: 1 });
    setNodePositions({});
  }, []);

  return (
    <div className="model-viewer-page">
      <header className="model-viewer-header">
        <div>
          <h1><Layers size={24} /> Modeling Viewer</h1>
          <p>Read-only semantic diagram viewer for ArchiMate, MBSE, SysML, and UML-derived model data.</p>
        </div>
        <div className="model-viewer-actions">
          <button type="button" onClick={loadView} disabled={status.loading}><RefreshCcw size={15} /> Refresh</button>
          <button type="button" onClick={() => onNavigate?.('graph')}><GitFork size={15} /> Graph Explorer</button>
        </div>
      </header>

      <section className="model-viewer-toolbar">
        <div className="model-viewer-tabs" role="tablist" aria-label="Model viewer modes">
          {VIEW_OPTIONS.map((view) => <button key={view.id} type="button" className={activeView === view.id ? 'active' : ''} onClick={() => { setActiveView(view.id); setQuery(''); setSelectedId(''); setTreeScope(null); setActiveRepresentationId(''); }}>{view.label}</button>)}
        </div>
        <label className="model-viewer-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter label, type, property, id" /></label>
        {(dataset.representations || []).length > 0 && <label className="model-viewer-representation"><span>Diagram</span><select value={activeRepresentationId} onChange={(event) => { setActiveRepresentationId(event.target.value); setSelectedId(''); setTreeScope(null); }}><option value="">All model</option>{dataset.representations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      </section>

      <section className="model-viewer-summary compact">
        <div><strong>{dataset.nodes.length}</strong><span>Elements</span></div>
        <div><strong>{dataset.links.length}</strong><span>Relationships</span></div>
        <div><strong>{query.trim() ? matchedNodes.length : visibleNodes.length}</strong><span>{query.trim() ? 'Matches' : 'Visible'}</span></div>
        <div><strong>{validation.length}</strong><span>Checks</span></div>
      </section>

      {status.error && <div className="model-viewer-error"><AlertTriangle size={16} /> {status.error}</div>}
      {!status.error && dataset.message && <div className="model-viewer-note">{dataset.message}</div>}


      <main className="model-viewer-layout tree-diagram">
        <section className="model-viewer-panel model-viewer-elements">
          <div className="panel-title"><Boxes size={16} /> Model Tree</div>
          <div className="model-tree">
            {treeGroups.map((group) => <section key={group.id} className="tree-group"><button type="button" className={`tree-group-header ${treeScope?.kind === 'layer' && treeScope.layer === group.id ? 'selected' : ''}`} style={{ color: group.color }} onClick={() => { setSelectedId(''); setTreeScope({ kind: 'layer', layer: group.id }); }}><span>{group.label}</span><small>{group.count}</small></button>{group.types.map((typeGroup) => <div key={`${group.id}-${typeGroup.type}`} className="tree-type"><button type="button" className={`tree-type-header ${treeScope?.kind === 'type' && treeScope.layer === group.id && treeScope.type === typeGroup.type ? 'selected' : ''}`} onClick={() => { setSelectedId(''); setTreeScope({ kind: 'type', layer: group.id, type: typeGroup.type }); }}><span className="tree-caret">▾</span><span>{typeGroup.type}</span><small>{typeGroup.count}</small></button>{typeGroup.nodes.map((node) => <button key={node.id} type="button" className={selectedNode?.id === node.id ? 'selected' : ''} onClick={() => { setTreeScope(null); setSelectedId(node.id); }}><span className="tree-branch" /><span className="type-dot" style={{ background: TYPE_COLORS[node.type] || group.color }} /><span><strong>{node.label}</strong></span></button>)}</div>)}</section>)}
            {visibleNodes.length === 0 && <div className="empty-state">No matching model elements.</div>}
          </div>
        </section>

        <section className="model-viewer-panel model-diagram-panel">
          <div className="panel-title"><Layers size={16} /> Main Representation <span className="diagram-count">{`${diagram.nodes.length} nodes / ${diagram.links.length} links`}</span>{(selectedNode || treeScope) && <button type="button" className="clear-selection" onClick={() => { setSelectedId(''); setTreeScope(null); }}>Show overview</button>}<button type="button" className="clear-selection" onClick={resetCanvasView}>Reset canvas</button></div>
          <div className="model-data-strip">
            <strong>{representationTitle}</strong>
            <span>{representationSubtitle}</span>
            {modelInfo.types.map(([type, count]) => <em key={type}>{type}: {count}</em>)}
          </div>
          {diagram.truncated && <div className="model-viewer-note compact">Showing first 140 contextual elements for readable diagram performance. Use search to narrow scope.</div>}
          <div className="semantic-canvas-wrap">
            <svg ref={svgRef} className="semantic-canvas" viewBox={`0 0 ${diagram.width} ${diagram.height}`} role="img" aria-label="Semantic model diagram" onWheel={handleCanvasWheel} onPointerDown={handleCanvasPointerDown} onPointerMove={handleCanvasPointerMove} onPointerUp={stopCanvasInteraction} onPointerLeave={stopCanvasInteraction}>
              <defs>
                <marker id="model-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" /></marker>
              </defs>
              <rect x="0" y="0" width={diagram.width} height={diagram.height} className="diagram-background" />
              <g className="diagram-content" transform={`translate(${canvasTransform.x} ${canvasTransform.y}) scale(${canvasTransform.k})`}>
              <g className="diagram-grid">
                {Array.from({ length: Math.ceil(diagram.width / 40) }).map((_, index) => <line key={`vx-${index}`} x1={index * 40} y1="0" x2={index * 40} y2={diagram.height} />)}
                {Array.from({ length: Math.ceil(diagram.height / 40) }).map((_, index) => <line key={`hy-${index}`} x1="0" y1={index * 40} x2={diagram.width} y2={index * 40} />)}
              </g>
              {diagram.nodes.length === 0 && <g><rect x="28" y="32" width="420" height="88" rx="8" fill="#ffffff" stroke="#d9e2ec" /><text x="52" y="74" className="empty-diagram-title">No diagram elements available</text><text x="52" y="98" className="empty-diagram-text">Import ArchiMate/MBSE data or clear the search filter.</text></g>}
              {diagram.links.map((link) => {
                const source = diagram.nodeMap.get(link.source);
                const target = diagram.nodeMap.get(link.target);
                if (!source || !target) return null;
                const x1 = source.x + source.width;
                const y1 = source.y + source.height / 2;
                const x2 = target.x;
                const y2 = target.y + target.height / 2;
                const midX = (x1 + x2) / 2;
                return <g key={link.id}><path d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`} className="diagram-edge" markerEnd="url(#model-arrow)" /><text x={midX - 36} y={(y1 + y2) / 2 - 5} className="edge-label">{link.type}</text></g>;
              })}
              {diagram.nodes.map((node) => {
                const isSelected = selectedNode?.id === node.id;
                return <g key={node.id} className={`diagram-node ${isSelected ? 'selected' : ''} ${query.trim() && matchedIds.has(node.id) ? 'matched' : ''}`} onPointerDown={(event) => handleNodePointerDown(event, node)} onClick={() => { setTreeScope(null); setSelectedId(node.id); }} tabIndex="0" role="button"><rect x={node.x} y={node.y} width={node.width} height={node.height} rx="7" fill="#ffffff" stroke={TYPE_COLORS[node.type] || '#64748b'} /><circle cx={node.x + 14} cy={node.y + 17} r="5" fill={TYPE_COLORS[node.type] || '#64748b'} /><text x={node.x + 26} y={node.y + 21} className="node-label">{node.label.slice(0, 24)}</text></g>;
              })}
              </g>
            </svg>
          </div>
        </section>

      </main>
    </div>
  );
}




















