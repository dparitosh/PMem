import { deduplicateNodesAndLinks, getLinkEndpointId } from './graphUtils';

// Rebuild from the original result plus branches whose roots are still visible.
// Complete slices retain shared nodes independently of response arrival order.
export function rebuildExpandedGraph(base, expansions, collapsedId) {
  const remaining = new Map(expansions);
  if (collapsedId !== undefined) remaining.delete(collapsedId);
  const supported = new Map();
  let graph = deduplicateNodesAndLinks(base?.nodes || [], base?.links || []);
  let changed = true;
  while (changed) {
    changed = false;
    const visible = new Set(graph.nodes.map(node => node.elementId));
    for (const [root, slice] of remaining) {
      if (supported.has(root) || !visible.has(root)) continue;
      supported.set(root, slice);
      graph = deduplicateNodesAndLinks([...graph.nodes, ...(slice.nodes || [])],
        [...graph.links, ...(slice.links || [])]);
      changed = true;
    }
  }
  const visible = new Set(graph.nodes.map(node => node.elementId));
  graph.links = graph.links.filter(link => visible.has(getLinkEndpointId(link.source))
    && visible.has(getLinkEndpointId(link.target)));
  return { graph, expansions: supported };
}

export function boundExpansionSlice(current, incoming, maxNodes) {
  const existing = new Set((current.nodes || []).map(node => node.elementId));
  const allowed = new Set(existing);
  let truncated = false;
  for (const node of incoming.nodes || []) {
    if (allowed.has(node.elementId)) continue;
    if (allowed.size >= maxNodes) { truncated = true; continue; }
    allowed.add(node.elementId);
  }
  return { nodes: (incoming.nodes || []).filter(node => allowed.has(node.elementId)),
    links: (incoming.links || []).filter(link => allowed.has(getLinkEndpointId(link.source))
      && allowed.has(getLinkEndpointId(link.target))), truncated };
}

// D3 must animate the same objects that the SVG binds, even for metadata-only updates.
export function reconcileSimulationNodes(incoming, current = [], idKey = 'elementId') {
  const previous = new Map(current.map(node => [node[idKey], node]));
  return incoming.map(node => {
    const existing = previous.get(node[idKey]);
    if (!existing) return { ...node };
    const position = {};
    for (const key of ['x', 'y', 'vx', 'vy', 'fx', 'fy', 'index']) {
      if (Number.isFinite(existing[key]) || existing[key] === null) position[key] = existing[key];
    }
    Object.assign(existing, node, position);
    return existing;
  });
}

export function graphTopologyKey(nodes, links, idKey = 'elementId') {
  const endpoint = value => typeof value === 'object' && value !== null
    ? value[idKey] : value;
  return JSON.stringify([
    nodes.map(node => String(node[idKey])).sort(),
    links.map(link => [String(link.elementId || link.id || ''),
      String(endpoint(link.source)), String(endpoint(link.target)), String(link.type || link.kind || '')])
      .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right))),
  ]);
}

export function seedSimulationNodes(nodes, width, height, idKey = 'elementId') {
  nodes.forEach(node => {
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) return;
    let hash = 2166136261;
    for (const character of String(node[idKey])) {
      hash = Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0;
    }
    const angle = (hash / 4294967296) * Math.PI * 2;
    const radius = Math.sqrt(((hash >>> 8) % 65536) / 65536) * Math.min(width, height) * 0.36;
    node.x = width / 2 + Math.cos(angle) * radius;
    node.y = height / 2 + Math.sin(angle) * radius;
  });
  return nodes;
}

export function oneHopCodeTrace(nodes, edges, query) {
  const term = String(query || '').trim().toLowerCase();
  if (!term) return { nodes, edges };
  const roots = new Set(nodes.filter(node => String(node.id).toLowerCase().includes(term)).map(node => node.id));
  const visible = new Set(roots);
  edges.forEach(edge => {
    if (roots.has(edge.source) || roots.has(edge.target)) {
      visible.add(edge.source);
      visible.add(edge.target);
    }
  });
  return { nodes: nodes.filter(node => visible.has(node.id)),
    edges: edges.filter(edge => visible.has(edge.source) && visible.has(edge.target)) };
}
