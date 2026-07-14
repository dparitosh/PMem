import { normalizePage, pageLabel } from './navigation';

test('normalizes aliases and rejects unknown or malformed pages', () => {
  expect(normalizePage(' metadata-registry ')).toBe('registry');
  expect(normalizePage('REQIF')).toBe('requirements');
  expect(normalizePage('removed-page')).toBe('graph');
  expect(normalizePage(null)).toBe('graph');
});

test('uses a safe label fallback', () => {
  expect(pageLabel('reports')).toBe('Reports');
  expect(pageLabel('unknown')).toBe('Graph Explorer');
});
