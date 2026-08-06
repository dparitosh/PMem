import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { RefreshCw, Search } from 'lucide-react';
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
  : `${languageLabel(item.language)} · ${item.lines} lines · ${item.architecture_role || (item.test ? 'test' : 'application')} · rank ${Number(item.rank_score || 0).toFixed(1)} · priority ${Number(item.streamline_priority || 0).toFixed(1)}`;

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

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError('');
    try {
      const response = await apiClient.get('/api/v1/code-audit', { params: { refresh } });
      setReport(response.data);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError.message || 'Unable to load code network');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);
  useEffect(() => {
    if (!live) return undefined;
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
  }, [live, load]);

  const rawGraph = useMemo(() => {
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
  }, [report, query, viewMode]);

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

  useEffect(() => {
    if (!svgRef.current || !graph.nodes.length) return undefined;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    const width = svgRef.current.clientWidth || 1100;
    const height = svgRef.current.clientHeight || 620;
    const nodes = graph.nodes.map((item) => ({ ...item }));
    const links = graph.edges.map((item) => ({ ...item }));
    const root = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.2, 5]).on('zoom', (event) => root.attr('transform', event.transform)));
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
  }, [graph, viewMode]);

  return (
    <div className="depo-page code-network">
      <div className="code-network__toolbar">
        <label className="code-network__search"><Search size={16} /><span className="sr-only">Filter files</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter files..." />
        </label>
        <button type="button" onClick={() => load(true)} disabled={loading}><RefreshCw size={16} /> Refresh audit</button>
        <label className="code-network__mode">
          <span>Detail</span>
          <select value={viewMode} onChange={(event) => { setViewMode(event.target.value); setSelected(null); }}>
            <option value="modules">Packages</option>
            <option value="ranked">Ranked backbone</option>
            <option value="files">All files</option>
          </select>
        </label>
        <label className="code-network__live">
          <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} /> Live updates
        </label>
        <span>{graph.nodes.length} {viewMode === 'modules' ? 'packages' : 'files'} · {graph.edges.length} weighted connections</span>
      </div>
      {error && <div className="code-network__message is-error">{error}</div>}
      {loading && !report && <div className="code-network__message">Building code network…</div>}
      {!loading && !error && !graph.nodes.length && <div className="code-network__message">No matching source files.</div>}
      <div className="code-network__canvas" hidden={!graph.nodes.length}>
        <svg ref={svgRef} role="img" aria-label="Repository source dependency network" />
        {selected && <aside className="code-network__detail">
          <strong>{selected.id}</strong>
          <span>{itemSummary(selected)}</span>
        </aside>}
        {tooltip && <div className="code-network__tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <strong>{tooltip.item.id}</strong>
          <span>{itemSummary(tooltip.item)}</span>
        </div>}
      </div>
    </div>
  );
}
