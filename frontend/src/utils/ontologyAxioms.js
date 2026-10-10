// Normalize relationship transport formats without counting arbitrary triples as axioms.
export function normalizeAxiomEdges(edges = [], nodes = []) {
  const ids = new Map();
  nodes.forEach(node => {
    const id = node.term_id || node.id;
    if (!id) return;
    for (const key of [id, node.uri, node.iri]) if (key) ids.set(String(key), id);
  });
  const ref = value => {
    const raw = typeof value === 'object' && value ? value.term_id || value.id || value.iri || value.uri : value;
    return ids.get(String(raw || '')) || String(raw || '');
  };
  const seen = new Set();
  return (Array.isArray(edges) ? edges : []).flatMap(edge => {
    const source = ref(edge.source_term ?? edge.source ?? edge.start);
    const target = ref(edge.target_term ?? edge.target ?? edge.end);
    const rawType = String(edge.mapping_type || edge.predicate || edge.type || edge.relationship_type || '');
    const local = rawType.split(/[#/]/).pop().replace(/^(rdfs|owl):/, '');
    const type = local.toLowerCase() === 'domain' ? 'DOMAIN' : local.toLowerCase() === 'range' ? 'RANGE' : local;
    if (!source || !target || !type) return [];
    const key = JSON.stringify([source, type, target]);
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ ...edge, source_term: source, target_term: target, mapping_type: type }];
  });
}

export function mergePropertyAxiomRows(taxonomyRows, reasoningRows) {
  const rows = new Map(taxonomyRows.map(row => [row.id, row]));
  for (const row of reasoningRows) {
    const existing = rows.get(row.id);
    rows.set(row.id, { ...existing, ...row,
      domain: row.domain === 'Not declared' && existing ? existing.domain : row.domain,
      range: row.range === 'Not declared' && existing ? existing.range : row.range,
      axiomCount: Math.max(existing?.axiomCount || 0, row.axiomCount || 0),
    });
  }
  return [...rows.values()];
}
