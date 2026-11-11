import React from 'react';

const MAX_CHIPS = 12;

function FacetRow({ label, items, selected, onToggle }) {
  if (!items.length) return null;
  const shown = items.slice(0, MAX_CHIPS);
  return (
    <div className="graph-slice-row" role="group" aria-label={label}>
      <span className="graph-slice-label">{label}</span>
      {shown.map((item) => {
        const active = selected.includes(item.value);
        return (
          <button
            key={item.value}
            type="button"
            className="graph-slice-chip"
            aria-pressed={active}
            onClick={() => onToggle(item.value)}
          >
            {item.value} <span className="graph-slice-count">{item.count}</span>
          </button>
        );
      })}
      {items.length > MAX_CHIPS && <span className="graph-slice-more">+{items.length - MAX_CHIPS} more</span>}
    </div>
  );
}

// Slice (one value) and dice (several values across dimensions) over the focused view.
export default function GraphSliceBar({ facets, selectedNodeTypes, selectedRelationshipTypes, onToggleNodeType, onToggleRelationshipType, onClear }) {
  const hasSelection = selectedNodeTypes.length > 0 || selectedRelationshipTypes.length > 0;
  if (!facets.nodeTypes.length && !facets.relationshipTypes.length) return null;
  return (
    <div className="graph-slice-bar">
      <FacetRow label="Node type" items={facets.nodeTypes} selected={selectedNodeTypes} onToggle={onToggleNodeType} />
      <FacetRow label="Relationship" items={facets.relationshipTypes} selected={selectedRelationshipTypes} onToggle={onToggleRelationshipType} />
      {hasSelection && (
        <button type="button" className="graph-slice-clear" onClick={onClear}>Clear filters</button>
      )}
    </div>
  );
}
