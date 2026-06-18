import {
  deduplicateNodesAndLinks,
  getOneHopNeighborhood,
  isMetadataWrapperNode,
  mergeGraphData,
  normalizeGraphDataset,
  normalizeRelationshipType,
  normalizeSearchTerm,
  removeExpandedSubgraph,
  validateConnectivity,
} from './graphUtils';

test('normalizeGraphDataset removes metadata wrapper nodes and keeps valid relationships', () => {
  const payload = {
    nodes: [
      {
        elementId: 'n1',
        labels: ['Part'],
        properties: { name: 'Part A' },
      },
      {
        elementId: 'id12',
        labels: ['XmlTag'],
        properties: { name: 'id12' },
      },
    ],
    relationships: [
      {
        elementId: 'r1',
        start: 'n1',
        end: 'n1',
        type: 'RELATED_TO',
      },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes).toHaveLength(1);
  expect(result.nodes[0].elementId).toBe('n1');
  expect(result.links).toHaveLength(1);
  expect(result.links[0].source).toBe('n1');
  expect(result.links[0].target).toBe('n1');
});

test('normalizeGraphDataset can collapse hidden bridge nodes into direct visible trace edges', () => {
  const payload = {
    nodes: [
      {
        elementId: 'req1',
        labels: ['Requirement'],
        properties: { name: 'Requirement A', catalogue_id: 'REQ-1' },
      },
      {
        elementId: 'hidden1',
        labels: ['ProductInstance'],
        properties: { name: 'id5222' },
      },
      {
        elementId: 'part1',
        labels: ['Part'],
        properties: { name: 'Part A' },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'req1', end: 'hidden1', type: 'INSTANCEDREF' },
      { elementId: 'r2', start: 'hidden1', end: 'part1', type: 'PART_REF' },
    ],
  };

  const result = normalizeGraphDataset(payload, { collapseHiddenBridges: true });

  expect(result.nodes.map((n) => n.elementId)).toEqual(['req1', 'part1']);
  expect(result.links).toHaveLength(1);
  expect(result.links[0].source).toBe('req1');
  expect(result.links[0].target).toBe('part1');
  expect(result.links[0].properties.collapsed).toBe(true);
});

test('normalizeRelationshipType canonicalizes raw XML bridge codes into semantic relationship names', () => {
  expect(normalizeRelationshipType('MASTERREF')).toBe('MASTER_REFERENCE');
  expect(normalizeRelationshipType('RELATEDREFS')).toBe('RELATED_REFERENCE');
  expect(normalizeRelationshipType('SEG0SATISFY')).toBe('SATISFIES');
  expect(normalizeRelationshipType('part-ref')).toBe('PART_REFERENCE');
});

test('normalizeGraphDataset removes XML wrapper nodes even when they have display names', () => {
  const payload = {
    nodes: [
      {
        elementId: 'n1',
        labels: ['Part'],
        properties: { name: 'Part A' },
      },
      {
        elementId: 'xml1',
        labels: ['XmlTag'],
        properties: { name: 'AccessIntent' },
      },
    ],
    relationships: [],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['n1']);
});

test('deduplicateNodesAndLinks keeps a single copy of nodes and links', () => {
  const result = deduplicateNodesAndLinks(
    [
      { elementId: 'n1', name: 'A' },
      { elementId: 'n1', name: 'A duplicate' },
    ],
    [
      { elementId: 'r1', source: 'n1', target: 'n1' },
      { elementId: 'r1', source: 'n1', target: 'n1' },
    ]
  );

  expect(result.nodes).toHaveLength(1);
  expect(result.links).toHaveLength(1);
});

test('mergeGraphData unions graph slices without duplicates', () => {
  const result = mergeGraphData(
    { nodes: [{ elementId: 'n1' }], links: [{ elementId: 'r1', source: 'n1', target: 'n1' }] },
    { nodes: [{ elementId: 'n2' }], links: [{ elementId: 'r2', source: 'n1', target: 'n2' }] }
  );

  expect(result.nodes.map((n) => n.elementId)).toEqual(['n1', 'n2']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1', 'r2']);
});

test('getOneHopNeighborhood returns the root node and its direct neighbors only', () => {
  const result = getOneHopNeighborhood(
    {
      nodes: [{ elementId: 'root' }, { elementId: 'n1' }, { elementId: 'n2' }, { elementId: 'n3' }],
      links: [
        { elementId: 'r1', source: 'root', target: 'n1' },
        { elementId: 'r2', source: 'n2', target: 'n3' },
        { elementId: 'r3', source: 'root', target: 'n2' },
      ],
    },
    'root'
  );

  expect(result.nodes.map((n) => n.elementId)).toEqual(['root', 'n1', 'n2']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1', 'r3']);
});

test('removeExpandedSubgraph removes the requested expansion slice', () => {
  const result = removeExpandedSubgraph(
    {
      nodes: [{ elementId: 'root' }, { elementId: 'child' }, { elementId: 'keep' }],
      links: [
        { elementId: 'r1', source: 'root', target: 'child' },
        { elementId: 'r2', source: 'root', target: 'keep' },
      ],
    },
    ['child'],
    ['r1']
  );

  expect(result.nodes.map((n) => n.elementId)).toEqual(['root', 'keep']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r2']);
});

test('validateConnectivity flags orphan nodes', () => {
  const result = validateConnectivity({
    nodes: [{ elementId: 'n1' }, { elementId: 'n2' }],
    links: [{ elementId: 'r1', source: 'n1', target: 'n1' }],
  });

  expect(result.isConnected).toBe(false);
  expect(result.orphanNodeIds).toEqual(['n2']);
});

test('normalizeSearchTerm strips wildcard markers while preserving the query tokens', () => {
  expect(normalizeSearchTerm('REQ-*')).toBe('req');
  expect(normalizeSearchTerm('*bearing*')).toBe('bearing');
  expect(normalizeSearchTerm('---REQ_0001***')).toBe('req_0001');
  expect(normalizeSearchTerm('  *  ')).toBe('');
});

test('isMetadataWrapperNode hides technical id nodes but keeps requirement business nodes', () => {
  expect(isMetadataWrapperNode({
    elementId: 'pi1',
    labels: ['ProductInstance'],
    properties: { name: 'id5222' },
  })).toBe(true);

  expect(isMetadataWrapperNode({
    elementId: 'req1',
    labels: ['Requirement'],
    properties: {
      name: 'Ability to work in various environmental conditions',
      catalogue_id: 'REQ-000023',
    },
  })).toBe(false);
});
