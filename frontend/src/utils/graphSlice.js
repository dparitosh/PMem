// Slice and dice over an already-loaded graph. Pure and O(nodes + links).
// A slice selects values of one dimension; a dice combines several dimensions.
// An empty selection for a dimension means "no restriction" on that dimension.

const nodeKey = (node) => node?.elementId ?? node?.id;
const endpointKey = (endpoint) => (endpoint && typeof endpoint === 'object' ? nodeKey(endpoint) : endpoint);

export const relationshipTypeOf = (link) => String(link?.type ?? link?.label ?? 'RELATED');

// Count nodes per type and links per relationship type, for building filter chips.
export function facetCounts(data, nodeTypeOf) {
  const nodeTypes = new Map();
  const relationshipTypes = new Map();
  for (const node of data?.nodes || []) {
    const type = nodeTypeOf(node);
    nodeTypes.set(type, (nodeTypes.get(type) || 0) + 1);
  }
  for (const link of data?.links || []) {
    const type = relationshipTypeOf(link);
    relationshipTypes.set(type, (relationshipTypes.get(type) || 0) + 1);
  }
  const byCountThenName = (a, b) => b.count - a.count || a.value.localeCompare(b.value);
  return {
    nodeTypes: [...nodeTypes].map(([value, count]) => ({ value, count })).sort(byCountThenName),
    relationshipTypes: [...relationshipTypes].map(([value, count]) => ({ value, count })).sort(byCountThenName),
  };
}

export function sliceGraph(data, { nodeTypes = [], relationshipTypes = [] } = {}, nodeTypeOf) {
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  const links = Array.isArray(data?.links) ? data.links : [];
  const nodeFilter = nodeTypes.length ? new Set(nodeTypes) : null;
  const relationshipFilter = relationshipTypes.length ? new Set(relationshipTypes) : null;
  if (!nodeFilter && !relationshipFilter) return data;

  const keptNodes = nodeFilter ? nodes.filter((node) => nodeFilter.has(nodeTypeOf(node))) : nodes;
  const keptIds = new Set(keptNodes.map(nodeKey));
  const keptLinks = links.filter((link) => {
    if (relationshipFilter && !relationshipFilter.has(relationshipTypeOf(link))) return false;
    // Links need both endpoints present; this drops relationships whose nodes were sliced away.
    return keptIds.has(endpointKey(link.source)) && keptIds.has(endpointKey(link.target));
  });
  return { ...data, nodes: keptNodes, links: keptLinks };
}
