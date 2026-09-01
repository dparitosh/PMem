import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { AlertTriangle, FolderTree, Network, RefreshCw, Search } from 'lucide-react';
import { IxBadge, IxButton, IxCheckbox, IxInput, IxSelect, IxSelectItem } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import '../CSS/CodeAuditPage.css';

const languageLabel = (language) => ({
  '.py': 'Python', '.js': 'JavaScript', '.jsx': 'React', '.ts': 'TypeScript', '.tsx': 'React TS',
}[language] || language || 'Source');

const shortFileName = (path) => {
  const name = String(path || '').split('/').pop() || String(path || '');
  return name.length > 28 ? `${name.slice(0, 25)}…` : name;
};

const moduleGroup = (id) => {
  const parts = String(id || '').split('/');
  if (parts[0] === 'backend') return parts.length === 2 ? 'backend/runtime' : `backend/${parts[1]}`;
  if (parts[0] === 'frontend') {
    if (parts[1] === 'src' && parts[2]) return `frontend/${parts[2]}`;
    if (parts[1] === 'tests') return 'frontend/e2e-tests';
    return 'frontend/tooling';
  }
  return parts.length > 1 ? parts[0] : 'repository-entrypoints';
};

const itemSummary = (item) => item.files
  ? `${item.files} files · ${item.lines} lines · ${item.dependencies || 0} dependencies`
  : item.type === 'workspace' ? 'Repository root — click nodes to expand the code structure'
  : item.type === 'directory' ? `${item.path || item.label} · folder`
  : item.type === 'file' ? `${languageLabel(item.language)} · ${item.path || item.label}`
  : ['class', 'function'].includes(item.type) ? `${item.type} · ${item.qualified_name || item.label}${item.line ? ` · line ${item.line}` : ''}`
  : `${languageLabel(item.language)} · ${item.lines} lines · ${item.architecture_role || (item.test ? 'test' : 'application')} · rank ${Number(item.rank_score || 0).toFixed(1)} · priority ${Number(item.streamline_priority || 0).toFixed(1)}`;

const reviewHeadline = (report) => {
  const recommendations = report?.graph?.analysis?.recommendations || [];
  if (!recommendations.length) return 'No high-priority structural review item is currently identified.';
  const top = recommendations[0];
  return `${shortFileName(top.file)} — ${top.reasons.join(', ')}`;
};

export default function CodeAuditPage() {
  const svgRef = useRef(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [live, setLive] = useState(true);
  const [tooltip, setTooltip] = useState(null);
  const [viewMode, setViewMode] = useState('ranked');
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [showSemanticLinks, setShowSemanticLinks] = useState(false);
  const retryRef = useRef({ delayMs: 30000, timerId: null });

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError('');
    try {
      const response = await apiClient.get('/api/v1/code-audit', { params: { refresh } });
      setReport(response.data);
      setExpandedNodes((current) => current.size ? current : new Set([response.data?.hierarchy?.root].filter(Boolean)));
      retryRef.current.delayMs = 30000;
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError.message || 'Unable to load code network');
      retryRef.current.delayMs = Math.min(retryRef.current.delayMs * 2, 300000);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);
  useEffect(() => {
    if (!live) return undefined;
    const schedule = () => {
      retryRef.current.timerId = window.setTimeout(async () => {
        await load(true);
        if (live) schedule();
      }, retryRef.current.delayMs);
    };
    schedule();
    return () => {
      if (retryRef.current.timerId) window.clearTimeout(retryRef.current.timerId);
    };
  }, [live, load]);

  const rawGraph = useMemo(() => {
    if (viewMode === 'hierarchy') {
      const hierarchy = report?.hierarchy;
      if (!hierarchy?.root) return { nodes: [], edges: [] };
      const childrenByParent = new Map();
      (hierarchy.edges || []).filter((edge) => edge.kind === 'contains').forEach((edge) => {
        const children = childrenByParent.get(edge.source) || [];
        children.push(edge.target);
        childrenByParent.set(edge.source, children);
      });
      const nodeById = new Map((hierarchy.nodes || []).map((node) => [node.id, node]));
      const visible = new Set([hierarchy.root]);
      const addVisibleChildren = (id) => {
        if (!expandedNodes.has(id)) return;
        (childrenByParent.get(id) || []).forEach((childId) => {
          visible.add(childId);
          addVisibleChildren(childId);
        });
      };
      addVisibleChildren(hierarchy.root);
      const term = query.trim().toLowerCase();
      const nodes = Array.from(visible).map((id) => ({
        ...nodeById.get(id),
        childCount: (childrenByParent.get(id) || []).length,
      })).filter((node) => !term || [node.label, node.path, node.qualified_name, node.type].some((value) => String(value || '').toLowerCase().includes(term)));
      const visibleIds = new Set(nodes.map((node) => node.id));
      const containmentEdges = (hierarchy.edges || []).filter((edge) => edge.kind === 'contains' && visibleIds.has(edge.source) && visibleIds.has(edge.target));
      const semanticEdges = (hierarchy.edges || []).filter((edge) => edge.semantic && visibleIds.has(edge.source) && visibleIds.has(edge.target));
      return {
        nodes,
        edges: showSemanticLinks ? [...containmentEdges, ...semanticEdges.slice(0, 600)] : containmentEdges,
      };
    }
    let nodes = report?.graph?.nodes || [];
    let edges = report?.graph?.edges || [];
    if (viewMode === 'ranked') {
      const included = new Set(nodes.filter((node) => node.backbone).map((node) => node.id));
      nodes = nodes.filter((node) => included.has(node.id));
      edges = edges.filter((edge) => included.has(edge.source) && included.has(edge.target));
    }
    if (!query.trim()) return { nodes, edges };
    const term = query.trim().toLowerCase();
    const matching = new Set(nodes.filter((node) => node.id.toLowerCase().includes(term)).map((node) => node.id));
    edges.forEach((edge) => {
      if (matching.has(edge.source) || matching.has(edge.target)) {
        matching.add(edge.source);
        matching.add(edge.target);
      }
    });
    return {
      nodes: nodes.filter((node) => matching.has(node.id)),
      edges: edges.filter((edge) => matching.has(edge.source) && matching.has(edge.target)),
    };
  }, [report, query, viewMode, expandedNodes, showSemanticLinks]);

  const graph = useMemo(() => {
    if (viewMode !== 'modules') return rawGraph;
    const groups = new Map();
    const nodeGroup = new Map();
    rawGraph.nodes.forEach((node) => {
      const id = moduleGroup(node.id);
      nodeGroup.set(node.id, id);
      const group = groups.get(id) || {
        id, files: 0, lines: 0, testFiles: 0, members: [],
        domain: id.startsWith('backend/') ? 'backend' : id.startsWith('frontend/') ? 'frontend' : 'tooling',
      };
      group.files += 1;
      group.lines += node.lines || 0;
      group.testFiles += node.test ? 1 : 0;
      group.members.push(node.id);
      groups.set(id, group);
    });
    const edgeGroups = new Map();
    rawGraph.edges.forEach((edge) => {
      const source = nodeGroup.get(edge.source);
      const target = nodeGroup.get(edge.target);
      if (!source || !target || source === target) return;
      const key = `${source}\u0000${target}\u0000${edge.kind || 'import'}`;
      const grouped = edgeGroups.get(key) || { source, target, kind: edge.kind || 'import', weight: 0, endpoints: new Set() };
      grouped.weight += 1;
      (edge.endpoints || []).forEach((endpoint) => grouped.endpoints.add(endpoint));
      edgeGroups.set(key, grouped);
    });
    const edges = Array.from(edgeGroups.values()).map((edge) => ({ ...edge, endpoints: Array.from(edge.endpoints).sort() }));
    const dependencies = new Map();
    edges.forEach((edge) => {
      dependencies.set(edge.source, (dependencies.get(edge.source) || 0) + edge.weight);
      dependencies.set(edge.target, (dependencies.get(edge.target) || 0) + edge.weight);
    });
    return {
      nodes: Array.from(groups.values()).map((node) => ({ ...node, dependencies: dependencies.get(node.id) || 0 })),
      edges,
    };
  }, [rawGraph, viewMode]);

  const summary = report?.summary || {};
  const workspace = report?.workspace || {};
  const selectedSymbols = useMemo(() => {
    if (viewMode !== 'hierarchy' || selected?.type !== 'file') return [];
    return (report?.hierarchy?.nodes || []).filter((node) => node.parent === selected.id && ['class', 'function'].includes(node.type));
  }, [report, selected, viewMode]);

  useEffect(() => {
    if (!svgRef.current || !graph.nodes.length) return undefined;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    const width = svgRef.current.clientWidth || 1100;
    const height = svgRef.current.clientHeight || 620;
    const nodes = graph.nodes.map((item) => ({ ...item }));
    const links = graph.edges.map((item) => ({ ...item }));
    const root = svg.append('g');
    const zoom = d3.zoom().scaleExtent([0.2, 5]).on('zoom', (event) => root.attr('transform', event.transform));
    svg.call(zoom);
    if (viewMode === 'hierarchy') {
      const nodeById = new Map(nodes.map((item) => [item.id, item]));
      const childrenByParent = new Map();
      const containmentLinks = links.filter((item) => item.kind === 'contains');
      containmentLinks.forEach((item) => {
        const children = childrenByParent.get(item.source) || [];
        children.push(item.target);
        childrenByParent.set(item.source, children);
      });
      const rootNode = nodeById.get(report?.hierarchy?.root);
      if (!rootNode) return undefined;
      const hierarchyRoot = d3.hierarchy(rootNode, (item) => (childrenByParent.get(item.id) || []).map((id) => nodeById.get(id)).filter(Boolean));
      const radius = Math.max(120, Math.min(width, height) / 2 - 72);
      d3.tree().size([Math.PI * 2, radius])(hierarchyRoot);
      const treeNodes = hierarchyRoot.descendants().map((item) => {
        const angle = item.x - Math.PI / 2;
        return {
          ...item.data,
          angle,
          x: width / 2 + item.y * Math.cos(angle),
          y: height / 2 + item.y * Math.sin(angle),
        };
      });
      const treeById = new Map(treeNodes.map((item) => [item.id, item]));
      const treeLinks = hierarchyRoot.links().map((item) => ({ source: treeById.get(item.source.data.id), target: treeById.get(item.target.data.id) }));
      const semanticLinks = links.filter((item) => item.semantic).map((item) => ({ ...item, source: treeById.get(item.source), target: treeById.get(item.target) })).filter((item) => item.source && item.target);
      root.append('g').attr('class', 'code-network__links').selectAll('line').data(treeLinks).join('line')
        .attr('class', 'is-containment')
        .attr('x1', (item) => item.source.x).attr('y1', (item) => item.source.y)
        .attr('x2', (item) => item.target.x).attr('y2', (item) => item.target.y);
      root.append('g').attr('class', 'code-network__semantic-links').selectAll('line').data(semanticLinks).join('line')
        .attr('class', (item) => `is-${item.kind}`)
        .attr('x1', (item) => item.source.x).attr('y1', (item) => item.source.y)
        .attr('x2', (item) => item.target.x).attr('y2', (item) => item.target.y)
        .append('title').text((item) => `${item.kind}: ${item.source.label} → ${item.target.label}`);
      const treeNode = root.append('g').attr('class', 'code-network__nodes').selectAll('circle').data(treeNodes).join('circle')
        .attr('r', (item) => item.type === 'workspace' ? 13 : item.type === 'directory' ? 10 : item.type === 'file' ? 7 : 5)
        .attr('class', (item) => `is-${item.type}${item.childCount ? ' is-expandable' : ''}`)
        .attr('role', 'button')
        .attr('tabindex', 0)
        .attr('aria-label', (item) => `${item.type} ${item.label}${item.childCount ? `, ${expandedNodes.has(item.id) ? 'collapse' : 'expand'} ${item.childCount} children` : ''}`)
        .attr('cx', (item) => item.x).attr('cy', (item) => item.y)
        .on('click', (_event, item) => {
          setSelected(item);
          if (item.childCount) setExpandedNodes((current) => {
            const next = new Set(current);
            if (next.has(item.id)) next.delete(item.id); else next.add(item.id);
            return next;
          });
        })
        .on('keydown', (event, item) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          setSelected(item);
          if (item.childCount) setExpandedNodes((current) => {
            const next = new Set(current);
            if (next.has(item.id)) next.delete(item.id); else next.add(item.id);
            return next;
          });
        })
        .on('mouseenter mousemove', (event, item) => {
          const [x, y] = d3.pointer(event, svgRef.current);
          setTooltip({ x: Math.max(8, x), y: Math.max(62, y), item });
        }).on('mouseleave', () => setTooltip(null));
      treeNode.append('title').text((item) => `${item.type}: ${item.qualified_name || item.path || item.label}${item.childCount ? ` (${item.childCount} children; click to ${expandedNodes.has(item.id) ? 'collapse' : 'expand'})` : ''}`);
      root.append('g').attr('class', 'code-network__labels code-network__radial-labels').selectAll('text').data(treeNodes).join('text')
        .attr('text-anchor', (item) => item.type === 'workspace' ? 'middle' : Math.cos(item.angle) >= 0 ? 'start' : 'end')
        .attr('transform', (item) => {
          if (item.type === 'workspace') return `translate(${item.x},${item.y + 4})`;
          const rotation = item.angle * 180 / Math.PI;
          const flip = Math.cos(item.angle) < 0 ? 180 : 0;
          return `translate(${item.x},${item.y}) rotate(${rotation + flip}) translate(12,4)`;
        })
        .text((item) => item.type === 'workspace' ? item.label : shortFileName(item.label));
      const focusedNode = selected ? treeById.get(selected.id) : null;
      if (focusedNode) {
        const focusTransform = d3.zoomIdentity.translate(width / 2 - focusedNode.x, height / 2 - focusedNode.y);
        svg.call(zoom.transform, focusTransform);
      }
      return undefined;
    }
    const link = root.append('g').attr('class', 'code-network__links').selectAll('line').data(links).join('line')
      .attr('class', (item) => item.kind === 'api_call' ? 'is-api-call' : item.kind === 'lazy_import' ? 'is-lazy-import' : 'is-import')
      .style('stroke-width', (item) => Math.min(4, 0.7 + Math.sqrt(item.weight || 1) * 0.45));
    link.append('title').text((item) => item.kind === 'api_call'
      ? `API: ${(item.endpoints || []).join(', ')}`
      : item.kind === 'lazy_import' ? 'Runtime/lazy import' : 'Import-time dependency');
    const node = root.append('g').attr('class', 'code-network__nodes').selectAll('circle').data(nodes).join('circle')
      .attr('r', (item) => item.files ? Math.min(22, 7 + Math.sqrt(item.files) * 2) : Math.min(15, 4 + Math.sqrt(item.lines || 1) / 10 + Number(item.rank_score || 0) / 18))
      .attr('class', (item) => `${item.domain === 'backend' || item.language === '.py' ? 'is-python' : item.test ? 'is-test' : 'is-frontend'}${Number(item.streamline_priority || 0) >= 50 ? ' is-priority' : ''}`)
      .on('click', (_event, item) => setSelected(item))
      .on('mouseenter mousemove', (event, item) => {
        const [x, y] = d3.pointer(event, svgRef.current);
        const tooltipWidth = Math.min(480, Math.max(240, width - 24));
        setTooltip({
          x: Math.max(8, Math.min(x, width - tooltipWidth - 8)),
          y: Math.max(62, Math.min(y, height - 8)),
          item,
        });
      })
      .on('mouseleave', () => setTooltip(null));
    const labels = root.append('g').attr('class', 'code-network__labels').selectAll('text').data(nodes).join('text')
      .text((item) => item.files ? item.id : shortFileName(item.id));
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((item) => item.id).distance(viewMode === 'modules' ? 130 : viewMode === 'ranked' ? 80 : 45).strength(0.35))
      .force('charge', d3.forceManyBody().strength(viewMode === 'modules' ? -420 : viewMode === 'ranked' ? -150 : -55))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(10))
      .on('tick', () => {
        link.attr('x1', (item) => item.source.x).attr('y1', (item) => item.source.y)
          .attr('x2', (item) => item.target.x).attr('y2', (item) => item.target.y);
        node.attr('cx', (item) => item.x).attr('cy', (item) => item.y);
        labels.attr('x', (item) => item.x + 9).attr('y', (item) => item.y + 3);
      });
    node.call(d3.drag()
      .on('start', (event, item) => { if (!event.active) simulation.alphaTarget(0.3).restart(); item.fx = item.x; item.fy = item.y; })
      .on('drag', (event, item) => { item.fx = event.x; item.fy = event.y; })
      .on('end', (event, item) => { if (!event.active) simulation.alphaTarget(0); item.fx = null; item.fy = null; }));
    return () => simulation.stop();
  }, [graph, viewMode, report, expandedNodes, selected]);

  return (
    <div className="depo-page code-network">
      <div className="code-network__toolbar">
        <label className="code-network__search"><Search size={16} /><span className="sr-only">Filter files</span>
          <IxInput value={query} onValueChange={(event) => setQuery(event.detail)} placeholder="Filter files..." aria-label="Filter files" />
        </label>
        <IxButton type="button" variant="primary" onClick={() => load(true)} disabled={loading}><RefreshCw size={16} /> Refresh audit</IxButton>
        <label className="code-network__mode">
          <span>Detail</span>
          <IxSelect value={viewMode} onValueChange={(event) => { setViewMode(event.detail); setSelected(null); }} aria-label="Code network detail">
            <IxSelectItem value="modules" label="Packages" />
            <IxSelectItem value="ranked" label="Ranked backbone" />
            <IxSelectItem value="files" label="All files" />
            <IxSelectItem value="hierarchy" label="Radial hierarchy" />
          </IxSelect>
        </label>
        <label className="code-network__live">
          <IxCheckbox checked={live} onCheckedChange={(event) => setLive(event.detail)} label="Live updates" />
        </label>
        {viewMode === 'hierarchy' && <label className="code-network__live">
          <IxCheckbox checked={showSemanticLinks} onCheckedChange={(event) => setShowSemanticLinks(event.detail)} label="Show calls and inheritance" />
        </label>}
        <IxBadge className="code-network__count" type="label" variant="neutral" label={`${graph.nodes.length} ${viewMode === 'modules' ? 'packages' : viewMode === 'hierarchy' ? 'visible nodes' : 'files'} · ${viewMode === 'hierarchy' ? 'expand a folder, then select a file to reveal its classes and functions' : `${graph.edges.length} weighted connections`}`} />
      </div>
      {report && (
        <section className="code-network__overview" aria-label="Current workspace code review summary">
          <div className="code-network__workspace"><FolderTree size={18} aria-hidden="true" /><div><strong>{workspace.name || 'Current workspace'}</strong><span>{workspace.scope || 'current workspace'} · automatic source scan</span></div></div>
          <div className="code-network__metric"><strong>{summary.source_files || 0}</strong><span>source files</span></div>
          <div className="code-network__metric"><strong>{summary.dependency_edges || 0}</strong><span>dependencies</span></div>
          <div className="code-network__metric"><strong>{summary.module_cycles || 0}</strong><span>cycles</span></div>
          <div className="code-network__review"><AlertTriangle size={17} aria-hidden="true" /><div><span>Priority review</span><strong>{reviewHeadline(report)}</strong></div></div>
          <div className="code-network__metric"><Network size={17} aria-hidden="true" /><strong>{summary.backend_routes || 0}</strong><span>API routes</span></div>
        </section>
      )}
      {error && <div className="code-network__message is-error">{error}</div>}
      {loading && !report && <div className="code-network__message">Building code network…</div>}
      {!loading && !error && !graph.nodes.length && <div className="code-network__message">No matching source files.</div>}
      <div className={`code-network__canvas${viewMode === 'hierarchy' ? ' is-hierarchy' : ''}`} hidden={!graph.nodes.length}>
        <svg ref={svgRef} role="img" aria-label={viewMode === 'hierarchy' ? 'Expandable radial repository hierarchy' : 'Repository source dependency network'} />
        {selected && <aside className="code-network__detail">
          <strong>{selected.id}</strong>
          <span>{itemSummary(selected)}</span>
          {selectedSymbols.length > 0 && <div className="code-network__symbols">
            <strong>Classes & functions ({selectedSymbols.length})</strong>
            <div>{selectedSymbols.map((symbol) => <button type="button" key={symbol.id} className={`is-${symbol.type}`} onClick={() => setSelected(symbol)}>{symbol.type === 'class' ? 'Class' : 'Function'} · {symbol.label}{symbol.line ? ` (line ${symbol.line})` : ''}</button>)}</div>
          </div>}
        </aside>}
        {tooltip && <div className="code-network__tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <strong>{tooltip.item.id}</strong>
          <span>{itemSummary(tooltip.item)}</span>
        </div>}
      </div>
    </div>
  );
}
