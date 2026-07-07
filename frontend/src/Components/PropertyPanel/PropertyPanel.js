import React from 'react';

export default function PropertyPanel({ selection, onChange }) {
  if (!selection) return <aside className="property-panel">Select a node or relationship.</aside>;
  const properties = selection.properties || {};
  return <aside className="property-panel"><h3>{selection.label || selection.type || selection.id}</h3>{Object.entries(properties).map(([key, value]) => <label key={key}>{key}<input value={value ?? ''} onChange={(event) => onChange?.({ ...selection, properties: { ...properties, [key]: event.target.value } })} /></label>)}</aside>;
}
