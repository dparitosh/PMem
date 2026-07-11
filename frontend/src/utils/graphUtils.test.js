import {
  deduplicateNodesAndLinks,
  getOneHopNeighborhood,
  isMetadataWrapperNode,
  isRelationshipCarrierNode,
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

test('normalizeGraphDataset collapses general relation carriers into direct business edges by default', () => {
  const payload = {
    nodes: [
      {
        elementId: 'req1',
        labels: ['Requirement'],
        properties: { name: 'Requirement A', catalogue_id: 'REQ-1' },
      },
      {
        elementId: 'rel1',
        labels: ['GeneralRelation'],
        properties: { name: 'Seg0Satisfy', sub_type: 'Seg0Satisfy', related_count: '1' },
      },
      {
        elementId: 'part1',
        labels: ['Part'],
        properties: { name: 'Part A', part_number: 'P-1' },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'req1', end: 'rel1', type: 'TRACE_LINK' },
      { elementId: 'r2', start: 'rel1', end: 'part1', type: 'PART_REF' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['req1', 'part1']);
  expect(result.links).toHaveLength(1);
  expect(result.links[0].source).toBe('req1');
  expect(result.links[0].target).toBe('part1');
  expect(result.links[0].type).toBe('GENERAL_RELATION');
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

test('normalizeGraphDataset keeps STPX CAD business objects with id-like names', () => {
  const payload = {
    nodes: [
      {
        elementId: 'part-1',
        labels: ['PART'],
        properties: {
          name: 'id116',
          external_id: 'id116',
          semantic_role: 'product',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'view-1',
        labels: ['PART_VIEW'],
        properties: {
          name: 'id118',
          semantic_role: 'representation',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'name-1',
        labels: ['NAME'],
        properties: { name: 'id119' },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'part-1', end: 'view-1', type: 'REFERENCES' },
      { elementId: 'r2', start: 'part-1', end: 'name-1', type: 'PARENT_OF' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['part-1', 'view-1']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1']);
});

test('normalizeGraphDataset keeps STEP shape semantic objects', () => {
  const payload = {
    nodes: [
      {
        elementId: 'shape-1',
        labels: ['PRODUCT_DEFINITION_SHAPE'],
        properties: {
          name: 'id-shape',
          semantic_role: 'shape',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'aspect-1',
        labels: ['SHAPE_ASPECT'],
        properties: {
          name: 'mounting face',
          semantic_role: 'feature',
          is_cad_business_object: true,
        },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'shape-1', end: 'aspect-1', type: 'REFERENCES' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['shape-1', 'aspect-1']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1']);
});

test('normalizeGraphDataset keeps STPX transform geometry objects', () => {
  const payload = {
    nodes: [
      {
        elementId: 'rot-1',
        labels: ['ROTATION_MATRIX'],
        properties: {
          name: 'id-rotation',
          semantic_role: 'geometry',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'vec-1',
        labels: ['TRANSLATION_VECTOR'],
        properties: {
          name: 'id-vector',
          semantic_role: 'geometry',
          is_cad_business_object: true,
        },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'rot-1', end: 'vec-1', type: 'REFERENCES' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['rot-1', 'vec-1']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1']);
});

test('normalizeGraphDataset keeps STEP feature and annotation semantic objects', () => {
  const payload = {
    nodes: [
      {
        elementId: 'feature-1',
        labels: ['SHAPE_ASPECT'],
        properties: {
          name: 'mounting feature',
          semantic_role: 'feature',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'annotation-1',
        labels: ['DRAUGHTING_CALLOUT'],
        properties: {
          name: 'hole note',
          semantic_role: 'annotation',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'text-1',
        labels: ['TEXT_LITERAL'],
        properties: {
          name: 'Tighten evenly',
          semantic_role: 'annotation',
          is_cad_business_object: true,
        },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'feature-1', end: 'annotation-1', type: 'REFERENCES' },
      { elementId: 'r2', start: 'annotation-1', end: 'text-1', type: 'REFERENCES' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['feature-1', 'annotation-1', 'text-1']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1', 'r2']);
});

test('normalizeGraphDataset keeps PMI tolerance semantic objects', () => {
  const payload = {
    nodes: [
      {
        elementId: 'tol-1',
        labels: ['GEOMETRIC_TOLERANCE'],
        properties: {
          name: 'GT-1',
          semantic_role: 'geometric_tolerance',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'dim-1',
        labels: ['DIMENSIONAL_SIZE'],
        properties: {
          name: 'diameter',
          semantic_role: 'dimension',
          is_cad_business_object: true,
        },
      },
      {
        elementId: 'plusminus-1',
        labels: ['PLUS_MINUS_TOLERANCE'],
        properties: {
          name: 'id-tol',
          semantic_role: 'dimension_tolerance',
          is_cad_business_object: true,
        },
      },
    ],
    relationships: [
      { elementId: 'r1', start: 'tol-1', end: 'dim-1', type: 'REFERENCES' },
      { elementId: 'r2', start: 'plusminus-1', end: 'dim-1', type: 'REFERENCES' },
    ],
  };

  const result = normalizeGraphDataset(payload);

  expect(result.nodes.map((n) => n.elementId)).toEqual(['tol-1', 'dim-1', 'plusminus-1']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1', 'r2']);
});

test('deduplicateNodesAndLinks keeps a single copy of nodes and links', () => {
  const result = deduplicateNodesAndLinks(
    [
      { elementId: 'n1', name: 'A' },
      { elementId: 'n1', name: 'A duplicate' },
    ],
    [
      { elementId: 'r1', source: 'n1', target: 'n1', type: 'RELATED_TO' },
      { elementId: 'r1', source: 'n1', target: 'n1', type: 'RELATED_TO' },
    ]
  );

  expect(result.nodes).toHaveLength(1);
  expect(result.links).toHaveLength(1);
});

test('mergeGraphData unions graph slices without duplicates', () => {
  const result = mergeGraphData(
    { nodes: [{ elementId: 'n1' }], links: [{ elementId: 'r1', source: 'n1', target: 'n1', type: 'RELATED_TO' }] },
    { nodes: [{ elementId: 'n2' }], links: [{ elementId: 'r2', source: 'n1', target: 'n2', type: 'RELATED_TO' }] }
  );

  expect(result.nodes.map((n) => n.elementId)).toEqual(['n1', 'n2']);
  expect(result.links.map((l) => l.elementId)).toEqual(['r1', 'r2']);
});

test('getOneHopNeighborhood returns the root node and its direct neighbors only', () => {
  const result = getOneHopNeighborhood(
    {
      nodes: [{ elementId: 'root' }, { elementId: 'n1' }, { elementId: 'n2' }, { elementId: 'n3' }],
      links: [
        { elementId: 'r1', source: 'root', target: 'n1', type: 'RELATED_TO' },
        { elementId: 'r2', source: 'n2', target: 'n3', type: 'RELATED_TO' },
        { elementId: 'r3', source: 'root', target: 'n2', type: 'RELATED_TO' },
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
        { elementId: 'r1', source: 'root', target: 'child', type: 'RELATED_TO' },
        { elementId: 'r2', source: 'root', target: 'keep', type: 'RELATED_TO' },
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
    links: [{ elementId: 'r1', source: 'n1', target: 'n1', type: 'RELATED_TO' }],
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

test('isRelationshipCarrierNode flags general relation carriers but not business objects', () => {
  expect(isRelationshipCarrierNode({
    elementId: 'rel1',
    labels: ['GeneralRelation'],
    properties: { sub_type: 'Seg0Satisfy', related_count: '2' },
  })).toBe(true);

  expect(isRelationshipCarrierNode({
    elementId: 'part1',
    labels: ['Part'],
    properties: { name: 'Rotor', part_number: 'P-100' },
  })).toBe(false);
});
