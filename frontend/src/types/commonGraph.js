export const COMMON_GRAPH_SCHEMA = {
  node: ['id', 'label', 'type', 'properties', 'metadata', 'style'],
  link: ['id', 'source', 'target', 'type', 'properties', 'metadata'],
};

export function normalizeCommonNode(raw = {}) {
  const properties = raw.properties && typeof raw.properties === 'object' ? raw.properties : {};
  const metadata = raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {};
  const style = raw.style && typeof raw.style === 'object' ? raw.style : {};
  const id = String(raw.id || raw.elementId || raw.uid || properties.uid || properties.id || properties.name || '');
  if (!id) return null;
  const label = String(raw.label || raw.name || properties.label || properties.name || properties.title || id);
  const type = String(raw.type || raw.element_type || properties.type || properties.element_type || 'Element');
  return { id, label, type, properties, metadata, style, x: raw.x ?? properties.x, y: raw.y ?? properties.y };
}

export function normalizeCommonLink(raw = {}) {
  const properties = raw.properties && typeof raw.properties === 'object' ? raw.properties : {};
  const metadata = raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {};
  const source = String(raw.source || raw.start || properties.source || '');
  const target = String(raw.target || raw.end || properties.target || '');
  if (!source || !target) return null;
  const type = String(raw.type || raw.relationship_type || properties.type || 'RELATED_TO');
  const id = String(raw.id || raw.elementId || properties.id || `${source}:${type}:${target}`);
  return { id, source, target, type, properties, metadata };
}

export function normalizeCommonGraph(input = {}) {
  const nodesById = new Map();
  const linksById = new Map();
  (input.nodes || []).forEach((item) => {
    const node = normalizeCommonNode(item);
    if (node) nodesById.set(node.id, node);
  });
  (input.links || input.relationships || []).forEach((item) => {
    const link = normalizeCommonLink(item);
    if (link && nodesById.has(link.source) && nodesById.has(link.target)) linksById.set(link.id, link);
  });
  return { nodes: [...nodesById.values()], links: [...linksById.values()] };
}
