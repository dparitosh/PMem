import React from 'react';

function TreeNode({ node, onSelect }) {
  return <li><button type="button" onClick={() => onSelect?.(node)}>{node.label || node.name || node.id}</button>{Array.isArray(node.children) && node.children.length > 0 && <ul>{node.children.map((child) => <TreeNode key={child.id} node={child} onSelect={onSelect} />)}</ul>}</li>;
}

export default function ModelExplorer({ tree = [], onSelect }) {
  return <nav className="model-explorer" aria-label="Model Explorer"><ul>{tree.map((node) => <TreeNode key={node.id} node={node} onSelect={onSelect} />)}</ul></nav>;
}
