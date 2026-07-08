function semanticLayer(node = {}) {
  const type = String(node.type || node.properties?.type || '').toLowerCase();
  const text = [node.label, node.type, node.properties?.folder_path, node.properties?.path].join(' ').toLowerCase();
  if (/(requirement|constraint|goal|principle|driver|assessment|stakeholder|motivation)/.test(text)) return 'motivation';
  if (/(capability|courseofaction|resource|valuestream|strategy)/.test(text)) return 'strategy';
  if (/(business|operational|actor|role|performer|process|function)/.test(text)) return 'business';
  if (/(application|interface|dataobject|logical)/.test(text)) return 'application';
  if (/(technology|device|node|software|artifact|part|block|component|physical)/.test(text)) return 'technology';
  if (/(product|workpackage|deliverable|implementation|migration)/.test(text)) return 'implementation';
  if (/(package|folder|view)/.test(type)) return 'other';
  return 'other';
}

function columnsFor(count) {
  if (count <= 6) return 1;
  if (count <= 18) return 2;
  return 3;
}

export function gridLayout(nodes = [], options = {}) {
  const width = options.nodeWidth || 214;
  const height = options.nodeHeight || 74;
  const gapX = options.gapX || 92;
  const gapY = options.gapY || 58;
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
  const layerOrder = config.layers || ['motivation', 'strategy', 'business', 'application', 'technology', 'implementation', 'other'];
  const grouped = new Map();
  nodes.forEach((node) => {
    const layer = node.metadata?.layer || node.style?.layer || node.properties?.layer || semanticLayer(node);
    if (!grouped.has(layer)) grouped.set(layer, []);
    grouped.get(layer).push(node);
  });

  const orderedLayers = [...new Set([...layerOrder, ...grouped.keys()])].filter((layer) => (grouped.get(layer) || []).length > 0);
  const incoming = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, 0]));
  links.forEach((link) => {
    outgoing.set(link.source, (outgoing.get(link.source) || 0) + 1);
    incoming.set(link.target, (incoming.get(link.target) || 0) + 1);
  });

  const positioned = [];
  const laneGap = 86;
  const nodeWidth = 214;
  const nodeHeight = 74;
  const rowGap = 58;
  const columnGap = 76;
  let yCursor = 96;

  orderedLayers.forEach((layer) => {
    const items = [...(grouped.get(layer) || [])].sort((a, b) => {
      const degree = (incoming.get(b.id) || 0) + (outgoing.get(b.id) || 0) - ((incoming.get(a.id) || 0) + (outgoing.get(a.id) || 0));
      if (degree !== 0) return degree;
      return String(a.label || '').localeCompare(String(b.label || ''));
    });
    const columns = columnsFor(items.length);
    items.forEach((node, index) => {
      const col = index % columns;
      const row = Math.floor(index / columns);
      positioned.push({
        ...node,
        x: Number.isFinite(Number(node.x)) ? Number(node.x) : 86 + col * (nodeWidth + columnGap),
        y: Number.isFinite(Number(node.y)) ? Number(node.y) : yCursor + row * (nodeHeight + rowGap),
        width: nodeWidth,
        height: nodeHeight,
        metadata: { ...(node.metadata || {}), layer },
      });
    });
    yCursor += Math.max(1, Math.ceil(items.length / columns)) * (nodeHeight + rowGap) + laneGap;
  });

  return positioned;
}
