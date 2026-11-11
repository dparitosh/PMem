// Pure graph-focus helpers: the neighbourhood of one node, bounded for rendering.
// Cost is O(nodes + links) per call; callers memoize on (data, focusId, depth).

export const MAX_FOCUS_NODES = 400;

const nodeKey = (node) => node?.elementId ?? node?.id;

const endpointKey = (endpoint) => (endpoint && typeof endpoint === 'object' ? nodeKey(endpoint) : endpoint);

export function focusNeighbourhood(data, focusId, depth = 1, maxNodes = MAX_FOCUS_NODES) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const links = Array.isArray(data?.links) ? data.links : [];
  if (focusId == null || !nodes.some((node) => nodeKey(node) === focusId)) return data;

  const adjacency = new Map();
  for (const link of links) {
    const source = endpointKey(link.source);
    const target = endpointKey(link.target);
    if (source == null || target == null) continue;
    if (!adjacency.has(source)) adjacency.set(source, new Set());
    if (!adjacency.has(target)) adjacency.set(target, new Set());
    adjacency.get(source).add(target);
    adjacency.get(target).add(source);
  }

  const limit = Math.max(1, Math.min(depth, 2));
  const visited = new Set([focusId]);
  let frontier = [focusId];
  let truncated = false;
  for (let hop = 0; hop < limit && frontier.length && !truncated; hop += 1) {
    const next = [];
    for (const id of frontier) {
      for (const neighbour of adjacency.get(id) || []) {
        if (visited.has(neighbour)) continue;
        if (visited.size >= maxNodes) { truncated = true; break; }
        visited.add(neighbour);
        next.push(neighbour);
      }
      if (truncated) break;
    }
    frontier = next;
  }

  return {
    ...data,
    nodes: nodes.filter((node) => visited.has(nodeKey(node))),
    links: links.filter((link) => visited.has(endpointKey(link.source)) && visited.has(endpointKey(link.target))),
    focus: { id: focusId, depth: limit, truncated },
  };
}
