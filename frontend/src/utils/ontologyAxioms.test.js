import { normalizeAxiomEdges, mergePropertyAxiomRows, deduplicateAxiomEdges } from './ontologyAxioms';

test('deduplicates large taxonomy slices once, preserving order and delimiter-containing identities', () => {
  const edges = Array.from({length: 100000}, (_, index) => ({source_term: `o:${index}`, mapping_type:'DOMAIN', target_term:'o:c'}));
  const result = deduplicateAxiomEdges([...edges, ...edges,
    {source_term:'a|b', mapping_type:'c', target_term:'d'},
    {source_term:'a', mapping_type:'b|c', target_term:'d'},
    {source_term:'', mapping_type:'DOMAIN', target_term:'o:c'}]);
  expect(result).toHaveLength(100002);
  expect(result[0]).toBe(edges[0]);
  expect(result[99999]).toBe(edges[99999]);
});

test('normalizes RDF predicate IRIs and graph endpoint formats without duplicate counts', () => {
  const edges = normalizeAxiomEdges([
    { source: 'urn:p', target: 'urn:c', predicate: 'http://www.w3.org/2000/01/rdf-schema#domain' },
    { source_term: 'o:p', target_term: 'o:c', mapping_type: 'DOMAIN' },
    { source: { id: 'o:p' }, target: { id: 'o:c' }, type: 'owl:equivalentProperty' },
  ], [{ term_id: 'o:p', uri: 'urn:p' }, { term_id: 'o:c', uri: 'urn:c' }]);
  expect(edges).toHaveLength(2);
  expect(edges[0].mapping_type).toBe('DOMAIN');
  expect(edges[1].mapping_type).toBe('equivalentProperty');
});

test('reasoning enriches property rows without erasing taxonomy axioms or other properties', () => {
  const rows = mergePropertyAxiomRows([
    { id: 'o:p', domain: 'Class', range: 'Target', axiomCount: 2 },
    { id: 'o:q', axiomCount: 1 },
  ], [{ id: 'o:p', domain: 'Not declared', range: 'Not declared', axiomCount: 0 }]);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toMatchObject({ domain: 'Class', range: 'Target', axiomCount: 2 });
});
