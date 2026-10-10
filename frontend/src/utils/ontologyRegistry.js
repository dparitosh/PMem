// Preserve immutable identities across native and legacy registry views.
export function registryCount(value) {
  if (value == null || value === '' || typeof value === 'boolean') return null;
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : null;
}
export function mergeOntologyMetadata(existing, incoming) {
  const merged = { ...existing };
  for (const field of ['prefix', 'ontology_prefix', 'namespace', 'source_namespace', 'target_namespace', 'data_product_draft']) {
    if (!merged[field]) merged[field] = incoming[field];
  }
  const isFormat = value => value && !['neo4j', 'neo4j_live', 'neo4j_projection'].includes(String(value).toLowerCase());
  for (const field of ['ontology_type', 'schema_format', 'file_type', 'type']) {
    if (!isFormat(merged[field]) && isFormat(incoming[field])) merged[field] = incoming[field];
  }
  return merged;
}

export function normalizeOntologyRows(rows = []) {
    return (Array.isArray(rows) ? rows : []).map((o) => {
      const value = o.ontology_id || o.id || o.prefix || o.value || o.name || o.ontology_prefix || '';
      const prefix = o.prefix || o.ontology_prefix || '';
      return {
        ...o,
        value,
        label: o.ontology_name || o.name || o.label || prefix || value,
        prefix,
        ontology_prefix: prefix,
        ontology_id: o.ontology_id || o.id || prefix,
        type: o.ontology_type || o.schema_format || o.type || o.file_type,
        source: o.source,
        namespace: o.namespace || o.source_namespace || o.target_namespace || '',
        source_namespace: o.source_namespace || o.namespace || '',
        target_namespace: o.target_namespace || o.namespace || '',
        status: o.status || o.availability,
        availability: o.availability || o.status,
        node_count: registryCount(o.node_count),
        relationship_count: registryCount(o.relationship_count),
        graph_available:
          Boolean(o.graph_available) ||
          registryCount(o.node_count) > 0 ||
          registryCount(o.relationship_count) > 0 ||
          String(o.status || o.availability || '').toLowerCase() === 'uploaded',
        disabled: Boolean(o.disabled),
        raw: o,
      };
    });
}
