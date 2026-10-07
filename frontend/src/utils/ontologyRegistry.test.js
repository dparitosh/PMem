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
