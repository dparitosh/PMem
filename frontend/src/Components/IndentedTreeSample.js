import React, { useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';

/*
  IndentedTreeSample
  ------------------
  Lightweight, self-contained sample component showing an indented tree layout
  with expand/collapse functionality using only React + D3 selection (no force simulation).

  Dummy domain: Projects -> Milestones -> Work Products -> Artifacts

  Features:
  - Expand / collapse triangles
  - Lazy flattening based on expansion state
  - Simple keyboard shortcut: Alt+E to expand all, Alt+C to collapse all
  - Styled alternating row backgrounds
  - Hover highlight
  - Purely client-side dummy data (no network calls)

  Usage:
    import IndentedTreeSample from './Components/IndentedTreeSample';
    <IndentedTreeSample width={800} height={500} />
*/

// Dummy hierarchical data model
const buildDummyData = () => [
  {
    id: 'proj-1',
    type: 'Project',
    name: 'Project Alpha',
    children: [
      {
        id: 'ms-1',
        type: 'Milestone',
        name: 'Design Freeze',
        children: [
          {
            id: 'wp-1',
            type: 'WorkProduct',
            name: 'Specification Doc',
            children: [
              { id: 'doc-1', type: 'Artifact', name: 'Spec_v1.pdf', children: [] },
              { id: 'doc-2', type: 'Artifact', name: 'Spec_v2.pdf', children: [] }
            ]
          },
          {
            id: 'wp-2',
            type: 'WorkProduct',
            name: 'Reference Design',
            children: [
              { id: 'cad-1', type: 'Artifact', name: 'Board.CAD', children: [] }
            ]
          }
        ]
      },
      {
        id: 'ms-2',
        type: 'Milestone',
        name: 'Prototype Build',
        children: [
          {
            id: 'wp-3',
            type: 'WorkProduct',
            name: 'Firmware',
            children: [
              { id: 'src-1', type: 'Artifact', name: 'main.c', children: [] },
              { id: 'src-2', type: 'Artifact', name: 'drivers.c', children: [] }
            ]
          }
        ]
      }
    ]
  },
  {
    id: 'proj-2',
    type: 'Project',
    name: 'Project Beta',
    children: [
      {
        id: 'ms-3',
        type: 'Milestone',
        name: 'Planning',
        children: []
      }
    ]
  }
];

// Generic hash-based color generation
const getTypeColor = (type) => {
  const hash = type.split('').reduce((a, b) => {
    a = ((a << 5) - a) + b.charCodeAt(0);
    return a & a;
  }, 0);
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 50%)`;
};

const ROW_HEIGHT = 34;
const INDENT = 24;

const IndentedTreeSample = ({ width = 700, height = 480 }) => {
  const data = useMemo(buildDummyData, []);
  const [expanded, setExpanded] = useState(() => new Set(data.map(d => d.id))); // expand top-level by default

  // Toggle expansion state
  const toggle = useCallback((id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  // Flatten based on expansion state
  const flat = useMemo(() => {
    const out = [];
    const walk = (node, depth) => {
      out.push({ ...node, depth });
      const isOpen = expanded.has(node.id);
      if (isOpen && node.children && node.children.length) {
        node.children.forEach(child => walk(child, depth + 1));
      }
    };
    data.forEach(root => walk(root, 0));
    return out;
  }, [data, expanded]);

  // Expand all / collapse all shortcuts
  const handleKey = useCallback((e) => {
    if (e.altKey && e.key.toLowerCase() === 'e') {
      // expand all
      const all = new Set();
      const collect = (nodes) => nodes.forEach(n => { all.add(n.id); if (n.children) collect(n.children); });
      collect(data);
      setExpanded(all);
    } else if (e.altKey && e.key.toLowerCase() === 'c') {
      // collapse all except roots
      setExpanded(new Set(data.map(d => d.id)));
    }
  }, [data]);

  React.useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  return (
    <div style={{ fontFamily: 'sans-serif', width, maxWidth: '100%' }}>
      <div style={{ marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
        <strong>Indented Tree Sample</strong>
        <span style={{ fontSize: 12, color: '#555' }}>Rows: {flat.length}</span>
        <button onClick={() => {
          const all = new Set();
          const collect = (nodes) => nodes.forEach(n => { all.add(n.id); if (n.children) collect(n.children); });
          collect(data);
          setExpanded(all);
        }} style={btnStyle}>Expand All</button>
        <button onClick={() => setExpanded(new Set(data.map(d => d.id)))} style={btnStyle}>Collapse To Roots</button>
        <span style={{ fontSize: 11, color: '#777' }}>Shortcuts: Alt+E / Alt+C</span>
      </div>
      <svg width={width} height={height} style={{ border: '1px solid #ddd', borderRadius: 6, background: '#fafafa' }}>
        {flat.map((node, i) => {
          const y = i * ROW_HEIGHT;
          const hasChildren = node.children && node.children.length > 0;
          const isExpanded = expanded.has(node.id);
          return (
            <g key={node.id} transform={`translate(0, ${y})`}>
              {/* Row background */}
              <rect x={0} y={0} width={width} height={ROW_HEIGHT - 1} fill={i % 2 === 0 ? '#fff' : '#f2f7fd'} stroke="#e1e5ea" />
              {/* Indent guide line */}
              {node.depth > 0 && (
                <line x1={INDENT * node.depth - 12} y1={0} x2={INDENT * node.depth - 12} y2={ROW_HEIGHT/2} stroke="#d0d7de" strokeWidth={1} />
              )}
              {/* Toggle triangle */}
              {hasChildren && (
                <g transform={`translate(${INDENT * node.depth + 10}, ${ROW_HEIGHT/2})`} style={{ cursor: 'pointer' }} onClick={() => toggle(node.id)}>
                  <rect x={-10} y={-10} width={20} height={20} fill="transparent" />
                  <path d="M -6 -6 L -6 6 L 6 0 Z" fill="#333" stroke="#111" strokeWidth={0.8} transform={isExpanded ? 'rotate(90)' : 'rotate(0)'} />
                </g>
              )}
              {/* Node circle */}
              <circle cx={INDENT * node.depth + (hasChildren ? 30 : 16)} cy={ROW_HEIGHT/2} r={10} fill={getTypeColor(node.type)} stroke="#fff" strokeWidth={2} />
              {/* Node type badge */}
              <rect x={INDENT * node.depth + (hasChildren ? 46 : 32)} y={ROW_HEIGHT/2 - 8} width={70} height={16} rx={8} fill={getTypeColor(node.type) + '22'} stroke={getTypeColor(node.type)} strokeWidth={1} />
              <text x={INDENT * node.depth + (hasChildren ? 81 : 67)} y={ROW_HEIGHT/2 + 4} fontSize={10} fontWeight="bold" textAnchor="middle" fill={getTypeColor(node.type)}>{node.type}</text>
              {/* Primary label */}
              <text x={INDENT * node.depth + (hasChildren ? 120 : 106)} y={ROW_HEIGHT/2 - 2} fontSize={13} fontWeight={600} fill="#212529">{node.name}</text>
              {/* Secondary info (demo) */}
              <text x={INDENT * node.depth + (hasChildren ? 120 : 106)} y={ROW_HEIGHT/2 + 12} fontSize={11} fill="#555">{hasChildren ? `${node.children.length} item${node.children.length!==1?'s':''}` : 'Leaf node'}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

const btnStyle = {
  padding: '6px 10px',
  fontSize: 12,
  border: '1px solid #ccc',
  borderRadius: 4,
  background: '#fff',
  cursor: 'pointer'
};

export default IndentedTreeSample;
