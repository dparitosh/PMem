const getLinkEndpointId = (endpoint) => {
  if (!endpoint) return null;
  if (typeof endpoint === 'object') {
    return endpoint.elementId || endpoint.id || endpoint.identity || null;
  }
  return endpoint;
};

export const normalizeGraphDataset = (payload) => {
  if (!payload) {
    return { nodes: [], links: [] };
  }

  if (Array.isArray(payload.nodes) && (Array.isArray(payload.relationships) || Array.isArray(payload.links))) {
    const rawRelationships = Array.isArray(payload.relationships) ? payload.relationships : payload.links;
    const nodes = payload.nodes
      .filter((node) => node?.elementId)
      .map((node) => ({
        ...(node.properties || {}),
        elementId: node.elementId,
        labels: node.labels || ['Node'],
        label: node.labels?.[0] || 'Node',
        properties: node.properties || {},
        can_traverse: node.can_traverse,
      }));

    const nodeIds = new Set(nodes.map((node) => node.elementId));
    const links = rawRelationships
      .filter((rel) => {
        const sourceId = rel?.start ?? getLinkEndpointId(rel?.source);
        const targetId = rel?.end ?? getLinkEndpointId(rel?.target);
        return rel?.elementId && nodeIds.has(sourceId) && nodeIds.has(targetId);
      })
      .map((rel) => ({
        elementId: rel.elementId,
        source: rel.start ?? getLinkEndpointId(rel.source),
        target: rel.end ?? getLinkEndpointId(rel.target),
        type: rel.type,
        properties: rel.properties || {},
      }));

    return { nodes, links };
  }

  if (Array.isArray(payload.results)) {
    const nodesMap = new Map();
    const rawLinks = new Map();

    payload.results.forEach((record) => {
      const n = record.n;
      const r = record.r;
      const m = record.m;

      if (n?.elementId && !nodesMap.has(n.elementId)) {
        nodesMap.set(n.elementId, {
          ...(n.properties || {}),
          elementId: n.elementId,
          labels: n.labels || ['Node'],
          label: n.labels?.[0] || 'Node',
          properties: n.properties || {},
          can_traverse: n.can_traverse,
        });
      }

      if (m?.elementId && !nodesMap.has(m.elementId)) {
        nodesMap.set(m.elementId, {
          ...(m.properties || {}),
          elementId: m.elementId,
          labels: m.labels || ['Node'],
          label: m.labels?.[0] || 'Node',
          properties: m.properties || {},
          can_traverse: m.can_traverse,
        });
      }

      if (r?.elementId && !rawLinks.has(r.elementId)) {
        rawLinks.set(r.elementId, {
          elementId: r.elementId,
          source: r.start,
          target: r.end,
          type: r.type,
          properties: r.properties || {},
        });
      }
    });

    const nodes = Array.from(nodesMap.values());
    const nodeIds = new Set(nodes.map((node) => node.elementId));
    const links = Array.from(rawLinks.values()).filter(
      (link) => nodeIds.has(link.source) && nodeIds.has(link.target)
    );
    return { nodes, links };
  }

  return { nodes: [], links: [] };
};
