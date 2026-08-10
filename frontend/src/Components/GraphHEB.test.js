import { normalizeGraphDataset } from '../utils/graphUtils';
import {
  buildNodeHighlightTerms,
  getNodeLabelStyle,
  getRelationshipLabelStyle,
  shouldRenderNodeLabels,
  shouldRenderRelationshipLabels,
  truncateGraphLabel,
} from '../utils/graphDisplayPolicy';

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

test('node labels are enabled for all graph view modes', () => {
  expect(shouldRenderNodeLabels(900, 1200, false, 'ontology')).toBe(true);
  expect(shouldRenderNodeLabels(900, 1200, false, 'individual')).toBe(true);
  expect(shouldRenderNodeLabels(900, 1200, false, 'full')).toBe(false);
  expect(shouldRenderNodeLabels(20, 12, true, 'ontology')).toBe(true);
});

test('dense overview graphs hide labels while search keeps them visible', () => {
  expect(shouldRenderNodeLabels(385, 375, false, 'full')).toBe(false);
  expect(shouldRenderNodeLabels(385, 375, false, 'ontology')).toBe(true);
  expect(shouldRenderRelationshipLabels(385, 375, false, 'ontology')).toBe(false);
});

test('dense graph labels are compact but not blank', () => {
  const style = getNodeLabelStyle(500, 'ontology');
  const label = truncateGraphLabel('Very Long Requirement Specification Node Name', style.maxLength);

  expect(style.fontSize).toBeLessThanOrEqual(9);
  expect(label).toMatch(/…$/);
  expect(label.length).toBeGreaterThan(0);
});

test('relationship labels are visible in focused graph modes and compact in dense graphs', () => {
  expect(shouldRenderRelationshipLabels(900, 1200, true, 'ontology')).toBe(false);
  expect(shouldRenderRelationshipLabels(900, 1200, false, 'individual')).toBe(true);
  expect(shouldRenderRelationshipLabels(80, 120, false, 'ontology')).toBe(true);
  expect(shouldRenderRelationshipLabels(40, 50, false, 'ontology')).toBe(true);
  expect(shouldRenderRelationshipLabels(40, 100, true, 'ontology')).toBe(true);

  const style = getRelationshipLabelStyle(220, 'ontology');
  expect(style.fontSize).toBeLessThanOrEqual(8);
  expect(truncateGraphLabel('Very Long Relationship Name', style.maxLength)).toMatch(/…$/);
});

test('highlight matching includes visible business labels beyond name', () => {
  const terms = buildNodeHighlightTerms({
    properties: {
      title: 'Bearing Life Requirement',
      code: 'REQ-006',
      part_number: 'SKF_6306-2Z',
    },
  });

  expect(terms).toEqual(expect.arrayContaining([
    'bearing life requirement',
    'req-006',
    'skf_6306-2z',
  ]));
});
