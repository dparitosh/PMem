export function toReactFlowElements(graph = {}) {
  return {
    nodes: (graph.nodes || []).map((node) => ({ id: node.id, position: { x: Number(node.x || 0), y: Number(node.y || 0) }, data: { label: node.label, ...node }, type: node.style?.reactFlowType || 'default' })),
    edges: (graph.links || []).map((link) => ({ id: link.id, source: link.source, target: link.target, label: link.type, data: link, type: 'smoothstep' })),
  };
}

export function fromReactFlowElements(nodes = [], edges = []) {
  return {
    nodes: nodes.map((node) => ({ id: node.id, label: node.data?.label || node.id, type: node.data?.type || 'Element', properties: node.data?.properties || {}, metadata: node.data?.metadata || {}, style: node.data?.style || {}, x: node.position?.x, y: node.position?.y })),
    links: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, type: edge.label || edge.data?.type || 'RELATED_TO', properties: edge.data?.properties || {}, metadata: edge.data?.metadata || {} })),
  };
}
