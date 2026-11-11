import { focusNeighbourhood, MAX_FOCUS_NODES } from './graphFocus';

const data = {
  nodes: [{ elementId: 'a' }, { elementId: 'b' }, { elementId: 'c' }, { elementId: 'd' }, { elementId: 'e' }],
  links: [
    { source: 'a', target: 'b' },
    { source: { elementId: 'b' }, target: { elementId: 'c' } },
    { source: 'c', target: 'd' },
    { source: 'e', target: 'e' },
  ],
};
const ids = (graph) => graph.nodes.map((node) => node.elementId).sort();

describe('focusNeighbourhood', () => {
  it('returns one-hop neighbours and the links between kept nodes', () => {
    const graph = focusNeighbourhood(data, 'b', 1);
    expect(ids(graph)).toEqual(['a', 'b', 'c']);
    expect(graph.links).toHaveLength(2);
    expect(graph.focus).toEqual({ id: 'b', depth: 1, truncated: false });
  });

  it('expands to two hops', () => {
    expect(ids(focusNeighbourhood(data, 'a', 2))).toEqual(['a', 'b', 'c']);
    expect(ids(focusNeighbourhood(data, 'b', 2))).toEqual(['a', 'b', 'c', 'd']);
  });

  it('accepts link endpoints given as node objects', () => {
    const graph = focusNeighbourhood(data, 'c', 1);
    expect(ids(graph)).toEqual(['b', 'c', 'd']);
  });

  it('returns the input unchanged when the focus node is absent', () => {
    expect(focusNeighbourhood(data, 'missing', 1)).toBe(data);
    expect(focusNeighbourhood(data, null, 1)).toBe(data);
  });

  it('keeps an isolated focus node alone', () => {
    expect(ids(focusNeighbourhood(data, 'e', 2))).toEqual(['e']);
  });

  it('bounds the number of nodes for rendering and reports truncation', () => {
    const nodes = Array.from({ length: MAX_FOCUS_NODES + 50 }, (_, i) => ({ elementId: `n${i}` }));
    const links = nodes.slice(1).map((node) => ({ source: 'n0', target: node.elementId }));
    const graph = focusNeighbourhood({ nodes, links }, 'n0', 1);
    expect(graph.nodes.length).toBeLessThanOrEqual(MAX_FOCUS_NODES);
    expect(graph.focus.truncated).toBe(true);
  });
});
