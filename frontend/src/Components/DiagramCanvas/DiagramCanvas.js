import React from 'react';

export default function DiagramCanvas({ graph = {}, selectedId, onSelect }) {
  const nodes = graph.nodes || [];
  const links = graph.links || [];
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  return <svg className="diagram-canvas" viewBox="0 0 1200 760" role="img" aria-label="Reusable diagram canvas">{links.map((link) => { const s = nodeMap.get(link.source); const t = nodeMap.get(link.target); if (!s || !t) return null; return <line key={link.id} x1={s.x || 0} y1={s.y || 0} x2={t.x || 0} y2={t.y || 0} stroke="#94a3b8" />; })}{nodes.map((node) => <g key={node.id} onClick={() => onSelect?.(node)}><rect x={node.x || 0} y={node.y || 0} width={node.width || 180} height={node.height || 56} rx="7" fill={selectedId === node.id ? '#dbeafe' : '#fff'} stroke={node.style?.stroke || '#64748b'} /><text x={(node.x || 0) + 12} y={(node.y || 0) + 30}>{node.label}</text></g>)}</svg>;
}
