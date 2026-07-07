export function gridLayout(nodes = [], options = {}) {
  const width = options.nodeWidth || 190;
  const height = options.nodeHeight || 62;
  const gapX = options.gapX || 78;
  const gapY = options.gapY || 52;
  const columns = Math.max(1, options.columns || Math.min(5, Math.ceil(Math.sqrt(Math.max(nodes.length, 1)))));
  return nodes.map((node, index) => ({
    ...node,
    x: Number.isFinite(Number(node.x)) ? Number(node.x) : 76 + (index % columns) * (width + gapX),
    y: Number.isFinite(Number(node.y)) ? Number(node.y) : 82 + Math.floor(index / columns) * (height + gapY),
    width,
    height,
  }));
}

export function layeredLayout(nodes = [], links = [], config = {}) {
  const layerOrder = config.layers || [];
  const layerFor = (node) => node.metadata?.layer || node.style?.layer || node.properties?.layer || 'other';
  const grouped = new Map();
  nodes.forEach((node) => {
    const layer = layerFor(node);
    if (!grouped.has(layer)) grouped.set(layer, []);
    grouped.get(layer).push(node);
  });
  const orderedLayers = [...new Set([...layerOrder, ...grouped.keys()])];
  const positioned = [];
  orderedLayers.forEach((layer, column) => {
    (grouped.get(layer) || []).forEach((node, row) => positioned.push({ ...node, x: 80 + column * 260, y: 90 + row * 96, width: 210, height: 62, metadata: { ...(node.metadata || {}), layer } }));
  });
  return positioned;
}
