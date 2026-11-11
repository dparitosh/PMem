import { facetCounts, relationshipTypeOf, sliceGraph } from './graphSlice';

const typeOf = (node) => node.type || 'Node';
const data = {
  nodes: [
    { elementId: 'p1', type: 'Part' },
    { elementId: 'p2', type: 'Part' },
    { elementId: 'm1', type: 'Material' },
    { elementId: 'x1', type: 'Process' },
  ],
  links: [
    { source: 'p1', target: 'p2', type: 'ASSEMBLED_WITH' },
    { source: 'p1', target: 'm1', type: 'MADE_OF' },
    { source: { elementId: 'p2' }, target: { elementId: 'x1' }, type: 'MACHINED_BY' },
    { source: 'm1', target: 'x1' },
  ],
};
const ids = (graph) => graph.nodes.map((node) => node.elementId).sort();

describe('sliceGraph', () => {
  it('returns the input unchanged when nothing is selected', () => {
    expect(sliceGraph(data, {}, typeOf)).toBe(data);
  });

  it('slices by node type and drops links to removed nodes', () => {
    const graph = sliceGraph(data, { nodeTypes: ['Part'] }, typeOf);
    expect(ids(graph)).toEqual(['p1', 'p2']);
    expect(graph.links.map((link) => relationshipTypeOf(link))).toEqual(['ASSEMBLED_WITH']);
  });

  it('slices by relationship type without removing nodes', () => {
    const graph = sliceGraph(data, { relationshipTypes: ['MADE_OF'] }, typeOf);
    expect(ids(graph)).toEqual(['m1', 'p1', 'p2', 'x1']);
    expect(graph.links).toHaveLength(1);
  });

  it('dices across node and relationship dimensions together', () => {
    const graph = sliceGraph(data, { nodeTypes: ['Part', 'Material'], relationshipTypes: ['MADE_OF', 'MACHINED_BY'] }, typeOf);
    expect(ids(graph)).toEqual(['m1', 'p1', 'p2']);
    expect(graph.links.map((link) => relationshipTypeOf(link))).toEqual(['MADE_OF']);
  });

  it('keeps an untyped link label as RELATED', () => {
    expect(relationshipTypeOf({ source: 'a', target: 'b' })).toBe('RELATED');
  });
});

describe('facetCounts', () => {
  it('counts node and relationship types, most frequent first', () => {
    const facets = facetCounts(data, typeOf);
    expect(facets.nodeTypes[0]).toEqual({ value: 'Part', count: 2 });
    expect(facets.relationshipTypes.map((item) => item.value)).toEqual(expect.arrayContaining(['ASSEMBLED_WITH', 'MADE_OF', 'MACHINED_BY', 'RELATED']));
  });
});
