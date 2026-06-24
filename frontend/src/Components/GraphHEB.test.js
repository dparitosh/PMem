import { normalizeGraphDataset } from '../utils/graphUtils';

test('normalizeGraphDataset preserves top-level can_traverse from graph responses', () => {
  const payload = {
    nodes: [
      {
        elementId: 'seed-1',
        labels: ['Product'],
        properties: { name: 'Seed' },
        can_traverse: true,
      },
    ],
    relationships: [],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes).toHaveLength(1);
  expect(result.nodes[0].elementId).toBe('seed-1');
  expect(result.nodes[0].can_traverse).toBe(true);
  expect(result.nodes[0].properties.name).toBe('Seed');
});

test('normalizeGraphDataset preserves top-level can_traverse from record-shaped responses', () => {
  const payload = {
    results: [
      {
        n: {
          elementId: 'seed-2',
          labels: ['Product'],
          properties: { name: 'Seed 2' },
          can_traverse: false,
        },
        r: null,
        m: null,
      },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes).toHaveLength(1);
  expect(result.nodes[0].elementId).toBe('seed-2');
  expect(result.nodes[0].can_traverse).toBe(false);
  expect(result.nodes[0].properties.name).toBe('Seed 2');
});
