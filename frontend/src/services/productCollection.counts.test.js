import { loadProductCollection } from './productCollection';

test('legacy loaded rows are not represented as a verified total', async () => {
  const value = await loadProductCollection(async () => ({ data: { products: [{ product_id: 'a', version: '1' }] } }));
  expect(value.total).toBeNull();
  expect(value.rows).toHaveLength(1);
});

test('explicitly completed pagination yields a count and excludes duplicate versions', async () => {
  const value = await loadProductCollection(async () => ({ data: { products: [{ product_id: 'a', version: '1' }, { product_id: 'a', version: '1' }], total: 1, next_offset: null } }));
  expect(value.total).toBe(1);
  expect(value.rows).toHaveLength(1);
  expect(value.warning).toMatch(/Duplicate/);
});
