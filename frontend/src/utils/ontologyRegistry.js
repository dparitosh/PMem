// Preserve immutable identities across native and legacy registry views.
export function normalizeOntologyRows(rows = []) {
    return (Array.isArray(rows) ? rows : []).map((o) => {
      const value = o.ontology_id || o.id || o.prefix || o.value || o.name || o.ontology_prefix || '';
      const prefix = o.prefix || o.ontology_prefix || o.ontology_id || o.id || value;
      return {
        ...o,
        value,
        label: o.ontology_name || o.name || o.label || value || prefix,
        prefix,
        ontology_prefix: prefix,
        ontology_id: o.ontology_id || o.id || prefix,
        type: o.file_type || o.type,
        source: o.source,
        namespace: o.namespace || o.source_namespace || o.target_namespace || '',
        source_namespace: o.source_namespace || o.namespace || '',
        target_namespace: o.target_namespace || o.namespace || '',
        status: o.status || o.availability,
        availability: o.availability || o.status,
        node_count: Number(o.node_count || o.neo4j_nodes_merged || 0),
        relationship_count: Number(o.relationship_count || o.neo4j_relationships_merged || 0),
        graph_available:
          Boolean(o.graph_available) ||
          Number(o.node_count || o.neo4j_nodes_merged || 0) > 0 ||
          Number(o.relationship_count || o.neo4j_relationships_merged || 0) > 0 ||
          String(o.status || o.availability || '').toLowerCase() === 'uploaded',
        disabled: Boolean(o.disabled),
        raw: o,
      };
    });
}
