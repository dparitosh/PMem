import { normalizeCommonGraph } from '../types/commonGraph';

function adjacencyFor(graph, directed = false) {
  const normalized = normalizeCommonGraph(graph);
  const adjacency = new Map(normalized.nodes.map((node) => [node.id, new Set()]));
  normalized.links.forEach((link) => {
    adjacency.get(link.source)?.add(link.target);
    if (!directed) adjacency.get(link.target)?.add(link.source);
  });
  return { graph: normalized, adjacency };
}

export function mineNeighborhood(input, rootId, depth = 1) {
  const { graph, adjacency } = adjacencyFor(input);
  const maxDepth = Math.max(0, Math.min(Number(depth) || 0, 10));
  if (!adjacency.has(String(rootId))) return { nodes: [], links: [] };
  const visited = new Set([String(rootId)]);
  let frontier = [String(rootId)];
  for (let level = 0; level < maxDepth && frontier.length; level += 1) {
    const next = [];
    frontier.forEach((id) => {
      adjacency.get(id)?.forEach((neighbor) => {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          next.push(neighbor);
        }
      });
    });
    frontier = next;
  }
  return {
    nodes: graph.nodes.filter((node) => visited.has(node.id)),
    links: graph.links.filter((link) => visited.has(link.source) && visited.has(link.target)),
  };
}

export function shortestPath(input, sourceId, targetId, directed = false) {
  const { adjacency } = adjacencyFor(input, directed);
  const source = String(sourceId);
  const target = String(targetId);
  if (!adjacency.has(source) || !adjacency.has(target)) return [];
  const queue = [source];
  const previous = new Map([[source, null]]);
  while (queue.length) {
    const current = queue.shift();
    if (current === target) break;
    adjacency.get(current)?.forEach((neighbor) => {
      if (!previous.has(neighbor)) {
        previous.set(neighbor, current);
        queue.push(neighbor);
      }
    });
  }
  if (!previous.has(target)) return [];
  const path = [];
  for (let current = target; current !== null; current = previous.get(current)) path.unshift(current);
  return path;
}

export function connectedComponents(input) {
  const { adjacency } = adjacencyFor(input);
  const remaining = new Set(adjacency.keys());
  const components = [];
  while (remaining.size) {
    const seed = remaining.values().next().value;
    const queue = [seed];
    const component = [];
    remaining.delete(seed);
    while (queue.length) {
      const current = queue.shift();
      component.push(current);
      adjacency.get(current)?.forEach((neighbor) => {
        if (remaining.delete(neighbor)) queue.push(neighbor);
      });
    }
    components.push(component.sort());
  }
  return components.sort((left, right) => right.length - left.length || left[0]?.localeCompare(right[0]));
}

export function mineGraph(input, options = {}) {
  const { graph, adjacency } = adjacencyFor(input);
  const nodeCount = graph.nodes.length;
  const degrees = graph.nodes.map((node) => {
    const degree = adjacency.get(node.id)?.size || 0;
    return {
      id: node.id,
      label: node.label,
      type: node.type,
      degree,
      degreeCentrality: nodeCount > 1 ? degree / (nodeCount - 1) : 0,
    };
  }).sort((left, right) => right.degree - left.degree || left.id.localeCompare(right.id));
  const components = connectedComponents(graph);
  const relationshipTypes = graph.links.reduce((counts, link) => {
    counts[link.type] = (counts[link.type] || 0) + 1;
    return counts;
  }, {});
  const hubLimit = Math.max(1, Math.min(Number(options.hubLimit) || 10, 100));
  return {
    nodeCount,
    relationshipCount: graph.links.length,
    componentCount: components.length,
    components,
    isolates: degrees.filter((entry) => entry.degree === 0),
    hubs: degrees.filter((entry) => entry.degree > 0).slice(0, hubLimit),
    degree: degrees,
    relationshipTypes,
  };
}
