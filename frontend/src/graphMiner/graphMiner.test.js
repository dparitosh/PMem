import { connectedComponents, mineGraph, mineNeighborhood, shortestPath } from './graphMiner';

const graph = {
  nodes: [
    { id: 'a', label: 'A' }, { id: 'b', label: 'B' }, { id: 'c', label: 'C' }, { id: 'd', label: 'D' },
  ],
  links: [
    { id: 'ab', source: 'a', target: 'b', type: 'USES' },
    { id: 'bc', source: 'b', target: 'c', type: 'USES' },
  ],
};

test('mines deterministic graph metrics and disconnected components', () => {
  const result = mineGraph(graph);
  expect(result.nodeCount).toBe(4);
  expect(result.componentCount).toBe(2);
  expect(result.hubs[0]).toMatchObject({ id: 'b', degree: 2 });
  expect(result.isolates.map((item) => item.id)).toEqual(['d']);
  expect(result.relationshipTypes).toEqual({ USES: 2 });
  expect(connectedComponents(graph)).toEqual([['a', 'b', 'c'], ['d']]);
});

test('mines bounded neighborhoods and shortest paths', () => {
  expect(mineNeighborhood(graph, 'a', 1).nodes.map((node) => node.id)).toEqual(['a', 'b']);
  expect(shortestPath(graph, 'a', 'c')).toEqual(['a', 'b', 'c']);
  expect(shortestPath(graph, 'a', 'd')).toEqual([]);
});
