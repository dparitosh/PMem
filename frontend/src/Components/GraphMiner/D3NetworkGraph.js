import React, { useEffect, useMemo, useRef } from 'react';
import * as d3 from 'd3';
import { normalizeCommonGraph } from '../../types/commonGraph';
import { mineGraph } from '../../graphMiner/graphMiner';

const TYPE_COLORS = ['#005ea8', '#008c95', '#7c3aed', '#b45309', '#166534', '#be123c', '#475569'];

export default function D3NetworkGraph({
  graph = {},
  selectedId,
  onSelect,
  onNodeDoubleClick,
  height = 520,
  showLabels = true,
  maxNodes = 1000,
}) {
  const hostRef = useRef(null);
  const normalized = useMemo(() => {
    const value = normalizeCommonGraph(graph);
    const nodes = value.nodes.slice(0, Math.max(1, maxNodes));
    const ids = new Set(nodes.map((node) => node.id));
    return { nodes, links: value.links.filter((link) => ids.has(link.source) && ids.has(link.target)) };
  }, [graph, maxNodes]);
  const metrics = useMemo(() => mineGraph(normalized), [normalized]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    let simulation;
    const render = () => {
      const width = Math.max(host.clientWidth || 0, 320);
      const canvasHeight = Math.max(Number(height) || 0, 280);
      const nodes = normalized.nodes.map((node) => ({ ...node }));
      const links = normalized.links.map((link) => ({ ...link }));
      const types = [...new Set(nodes.map((node) => node.type))].sort();
      const color = d3.scaleOrdinal(types, TYPE_COLORS);
      const svg = d3.select(host).selectAll('svg').data([null]).join('svg')
        .attr('width', '100%')
        .attr('height', canvasHeight)
        .attr('viewBox', `0 0 ${width} ${canvasHeight}`)
        .attr('role', 'img')
        .attr('aria-label', `Graph with ${nodes.length} nodes and ${links.length} relationships`);
      svg.selectAll('*').remove();
      const root = svg.append('g');
      svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', (event) => root.attr('transform', event.transform)));
      root.append('g').selectAll('line').data(links).join('line')
        .attr('stroke', '#9fb3c8').attr('stroke-opacity', 0.72).attr('stroke-width', 1.2);
      const node = root.append('g').selectAll('g').data(nodes, (item) => item.id).join('g')
        .attr('tabindex', 0)
        .attr('role', 'button')
        .attr('aria-label', (item) => `${item.label}, ${item.type}`)
        .style('cursor', 'pointer')
        .on('click', (_, item) => onSelect?.(item))
        .on('dblclick', (_, item) => onNodeDoubleClick?.(item))
        .on('keydown', (event, item) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect?.(item);
          }
        });
      node.append('circle')
        .attr('r', (item) => (item.id === selectedId ? 10 : 7))
        .attr('fill', (item) => color(item.type))
        .attr('stroke', (item) => (item.id === selectedId ? '#111827' : '#fff'))
        .attr('stroke-width', (item) => (item.id === selectedId ? 3 : 1.5));
      if (showLabels && nodes.length <= 250) {
        node.append('text').attr('x', 11).attr('y', 4).attr('font-size', 10)
          .attr('fill', '#243b53').text((item) => item.label);
      }
      simulation?.stop();
      simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id((item) => item.id).distance(72))
        .force('charge', d3.forceManyBody().strength(nodes.length > 300 ? -45 : -120))
        .force('center', d3.forceCenter(width / 2, canvasHeight / 2))
        .force('collide', d3.forceCollide(16))
        .on('tick', () => {
          root.selectAll('line')
            .attr('x1', (item) => item.source.x).attr('y1', (item) => item.source.y)
            .attr('x2', (item) => item.target.x).attr('y2', (item) => item.target.y);
          node.attr('transform', (item) => `translate(${item.x},${item.y})`);
        });
      node.call(d3.drag()
        .on('start', (event, item) => { if (!event.active) simulation.alphaTarget(0.3).restart(); item.fx = item.x; item.fy = item.y; })
        .on('drag', (event, item) => { item.fx = event.x; item.fy = event.y; })
        .on('end', (event, item) => { if (!event.active) simulation.alphaTarget(0); item.fx = null; item.fy = null; }));
    };
    render();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(render) : null;
    observer?.observe(host);
    return () => {
      observer?.disconnect();
      simulation?.stop();
      d3.select(host).selectAll('*').remove();
    };
  }, [height, normalized, onNodeDoubleClick, onSelect, selectedId, showLabels]);

  if (normalized.nodes.length === 0) return <div className="depo-empty">No graph data available.</div>;
  return (
    <section aria-label="Graph Miner visualization">
      <div ref={hostRef} style={{ minHeight: height, width: '100%' }} />
      <div className="depo-panel__meta" aria-live="polite" style={{ display: 'block' }}>
        {metrics.nodeCount} nodes · {metrics.relationshipCount} relationships · {metrics.componentCount} components
      </div>
    </section>
  );
}
