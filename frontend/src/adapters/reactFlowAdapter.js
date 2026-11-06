function semanticCategory(type = '') {
  const value = String(type).toLowerCase();
  if (/(requirement|constraint|goal|principle|driver|assessment|stakeholder)/.test(value)) return 'motivation';
  if (/(capability|courseofaction|resource|valuestream|strategy)/.test(value)) return 'strategy';
  if (/(business|operational|actor|role|performer|process|function)/.test(value)) return 'business';
  if (/(application|interface|dataobject|logical)/.test(value)) return 'application';
  if (/(technology|device|node|software|artifact|part|block|component|physical)/.test(value)) return 'technology';
  if (/(product|workpackage|deliverable|implementation|migration)/.test(value)) return 'implementation';
  return 'other';
}

function shapeForType(type = '') {
  const value = String(type).toLowerCase();
  if (/(package|folder)/.test(value)) return 'folder';
  if (/(view|diagram)/.test(value)) return 'view';
  if (/(requirement|constraint|goal|principle|driver|assessment)/.test(value)) return 'motivation';
  if (/(businessactor|actor|performer|role)/.test(value)) return 'actor';
  if (/(process|function|activity|capability|service)/.test(value)) return 'process';
  if (/(dataobject|artifact|document)/.test(value)) return 'document';
  if (/(node|device|systemsoftware|component|part|product)/.test(value)) return 'component';
  return 'element';
}

const CATEGORY_COLORS = {
  motivation: '#b45309',
  strategy: '#7c3aed',
  business: '#0f766e',
  application: '#005a9c',
  technology: '#166534',
  implementation: '#334155',
  other: '#64748b',
};

function readableRelationship(type = '') {
  return String(type || 'RELATED_TO')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

export function toReactFlowElements(graph = {}) {
  return {
    nodes: (graph.nodes || []).map((node) => {
      const category = node.metadata?.layer || node.style?.layer || semanticCategory(node.type);
      return {
        id: node.id,
        position: { x: Number(node.x || 0), y: Number(node.y || 0) },
        data: {
          label: node.label,
          ...node,
          metadata: { ...(node.metadata || {}), layer: category },
          style: {
            ...(node.style || {}),
            color: node.style?.color || CATEGORY_COLORS[category] || CATEGORY_COLORS.other,
            shape: node.style?.shape || shapeForType(node.type),
          },
        },
        type: node.style?.reactFlowType || 'semantic',
        width: node.width || 214,
        height: node.height || 72,
      };
    }),
    edges: (graph.links || []).map((link) => ({
      id: link.id,
      source: link.source,
      target: link.target,
      label: readableRelationship(link.type),
      data: { ...link, displayLabel: readableRelationship(link.type) },
      type: 'smoothstep',
    })),
  };
}

export function fromReactFlowElements(nodes = [], edges = []) {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      label: node.data?.label || node.id,
      type: node.data?.type || 'Element',
      properties: node.data?.properties || {},
      metadata: node.data?.metadata || {},
      style: node.data?.style || {},
      x: node.position?.x,
      y: node.position?.y,
      width: node.width || node.data?.width,
      height: node.height || node.data?.height,
    })),
    links: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.data?.type || edge.label || 'RELATED_TO',
      properties: edge.data?.properties || {},
      metadata: edge.data?.metadata || {},
    })),
  };
}
