import { expect, test } from 'vitest';
import { dictionaryAssetDraft, metadataAssetsPayload } from './metadataRegistryPayload';

test('registry validates empty and malformed responses', () => {
  expect(metadataAssetsPayload({ assets: [] })).toEqual([]);
  for (const value of [{}, { assets: null }, { assets: [null] }]) expect(() => metadataAssetsPayload(value)).toThrow();
  const asset = { asset_id: 'a', name: 'Asset', lifecycle_status: 'draft' };
  for (const field of ['definition', 'asset_type', 'domain', 'owner', 'steward', 'version']) {
    expect(() => metadataAssetsPayload({ assets: [{ ...asset, [field]: {} }] })).toThrow();
  }
  expect(metadataAssetsPayload({ assets: [{ ...asset, owner: null }] })).toHaveLength(1);
});
test('term identity is stable, isolated by ontology and remains draft', () => {
  const term = { term_id: 'ex:Part', label: 'Part', source: 'class' };
  const first = dictionaryAssetDraft(term, { ontology_id: 'a' });
  expect(first).toEqual(dictionaryAssetDraft(term, { ontology_id: 'a' }));
  expect(first.asset_id).not.toBe(dictionaryAssetDraft(term, { ontology_id: 'b' }).asset_id);
  expect(first.lifecycle_status).toBe('draft');
});
