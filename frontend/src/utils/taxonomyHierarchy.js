export function hierarchyEdge(edge) {
  return ['narrower', 'parentOf'].includes(edge.mapping_type)
    ? { ...edge, source_term: edge.target_term, target_term: edge.source_term } : edge;
}
