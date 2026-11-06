import { mergeOntologyMetadata, normalizeOntologyRows } from './ontologyRegistry';

test('merge fills source format while preserving native identity and known metadata', () => {
  const [native] = normalizeOntologyRows([{ ontology_id: 'native-id', file_type: 'neo4j', prefix: 'native' }]);
  const [legacy] = normalizeOntologyRows([{ ontology_id: 'native-id', file_type: 'xsd', prefix: 'legacy', data_product_draft: { contract: 'draft' } }]);
  const merged = mergeOntologyMetadata(native, legacy);
  expect(merged.ontology_id).toBe('native-id');
  expect(merged.prefix).toBe('native');
  expect(merged.file_type).toBe('xsd');
  expect(merged.data_product_draft.contract).toBe('draft');
  expect(mergeOntologyMetadata({ type: 'OWL' }, { type: 'XSD' }).type).toBe('OWL');
});

test('current zero counts are preserved and historical import counts are not live totals', () => {
  const [zero, unknown, invalid] = normalizeOntologyRows([
    { node_count: 0, relationship_count: 0, neo4j_nodes_merged: 25 },
    { neo4j_nodes_merged: 25 },
    { node_count: -1, relationship_count: 'invalid' },
  ]);
  expect(zero.node_count).toBe(0);
  expect(zero.relationship_count).toBe(0);
  expect(unknown.node_count).toBeNull();
  expect(invalid.node_count).toBeNull();
  expect(invalid.relationship_count).toBeNull();
});


test('graph discovery and catalog rows share canonical identity while preserving the registered name', () => {
  const [catalog, graph] = normalizeOntologyRows([
    {ontology_id: 'splm_123', ontology_name: 'Teamcenter PLMXML ontology', prefix: 'splm', file_type: 'owl'},
    {ontology_id: 'splm_123', ontology_name: 'splm', prefix: 'splm', source: 'neo4j', file_type: 'neo4j'},
  ]);
  expect(graph.value).toBe(catalog.value);
  expect(mergeOntologyMetadata(catalog, graph).label).toBe('Teamcenter PLMXML ontology');
});
