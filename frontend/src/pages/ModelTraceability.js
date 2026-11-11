import React from 'react';

export function safeReference(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    // Never turn credential-bearing source URLs into clickable links.
    if ([...url.searchParams.keys()].some(key => /token|secret|password|api.?key|signature|credential|^(sig|key|auth|code)$/i.test(key))) return null;
    return url.href;
  } catch { return null; }
}

export function collectReferences(element, context) {
  const result = new Map();
  const add = (node, relationship) => {
    const props = node?.properties || {};
    const evidence = `${node?.type || ''} ${(node?.labels || []).join(' ')} ${relationship || ''}`;
    for (const [field, raw] of Object.entries(props)) {
      if (!/url|href|uri|location|reference|dataset|cad|plm|simulation/i.test(field) || /^(iri|uri)$|ontology|namespace|vocabulary/i.test(field)) continue;
      for (const value of Array.isArray(raw) ? raw : [raw]) {
        const href = safeReference(value);
        if (!href) continue;
        const category = /simulation|cae|solver/i.test(field + ' ' + evidence) ? 'Simulation datasets'
          : /cad|geometry|drawing|stepfile/i.test(field + ' ' + evidence) ? 'CAD files'
          : /plm|teamcenter|windchill|enovia/i.test(field + ' ' + evidence) ? 'PLM records' : 'Other source references';
        result.set(`${category}|${href}`, {category, href, label: props.name || props.label || node.label || field,
          evidence: relationship ? `Recorded graph relationship: ${relationship}` : `Source property: ${field}`});
      }
    }
  };
  add({...element, properties: {...element?.properties, ...context?.properties}});
  for (const node of context?.nodes || []) {
    const relation = context.links?.find(link => link.source === node.id || link.target === node.id);
    if (relation) add(node, relation.type);
  }
  return [...result.values()];
}

export default function ModelTraceability({element, context, loading, error}) {
  const refs = collectReferences(element, context);
  return <section className="model-traceability" aria-label="Engineering traceability">
    <h3>Engineering traceability</h3>
    {loading && <p role="status">Checking recorded product and dataset associations…</p>}
    {error && <p role="alert">{error}</p>}
    {['PLM records','CAD files','Simulation datasets','Other source references'].map(category => {
      const items = refs.filter(item => item.category === category);
      return <div key={category}><strong>{category} · {items.length} web references</strong>
        {items.length ? <ul>{items.map(item => <li key={item.href}><a href={item.href} target="_blank" rel="noopener noreferrer">{item.label} ↗</a><small>{item.evidence}. Destination access is checked by the source system.</small></li>)}</ul>
          : <p>No recorded web link in the available evidence.</p>}</div>;
    })}
    {Boolean(context?.nodes?.length) && <details><summary>Recorded graph references ({context.nodes.length})</summary><p>Includes vocabulary and schema references; these are not evidence of a CAD file or simulation result.</p><ul>{context.nodes.map((node,index)=><li key={`${node.id}:${index}`}>{node.properties?.label || node.properties?.name || node.id}<small>{String(context.links?.find(link=>link.source===node.id || link.target===node.id)?.type || 'Recorded association').split(/[#/]/).pop()} · {node.id}</small></li>)}</ul></details>}
    {context?.truncated && <p role="status">Showing the first 100 graph associations. Additional associations may exist.</p>}
    {context?.message && <p>{context.message}</p>}
    <p>References preserve source evidence; they do not certify revision compatibility, access or engineering approval.</p>
  </section>;
}
