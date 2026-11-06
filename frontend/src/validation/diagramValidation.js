export function validateGraphAgainstConfig(graph = {}, config = {}) {
  const issues = [];
  const nodeIds = new Set((graph.nodes || []).map((node) => node.id));
  const seenIds = new Set();
  const duplicateIds = new Set();
  (graph.nodes || []).forEach((node) => {
    if (seenIds.has(node.id)) duplicateIds.add(node.id);
    seenIds.add(node.id);
    const required = config.requiredProperties?.[node.type] || config.requiredProperties?.default || ['name'];
    required.forEach((key) => {
      const value = node.properties?.[key] ?? node[key];
      if (value === undefined || value === null || String(value).trim() === '') {
        issues.push({ severity: 'warning', rule: 'missing_required_property', nodeId: node.id, message: `${node.label || node.id} is missing ${key}.` });
      }
    });
  });
  duplicateIds.forEach((id) => issues.push({ severity: 'error', rule: 'duplicate_id', nodeId: id, message: `Duplicate node id ${id}.` }));
  const degree = new Map([...nodeIds].map((id) => [id, 0]));
  (graph.links || []).forEach((link) => {
    if (!nodeIds.has(link.source) || !nodeIds.has(link.target)) {
      issues.push({ severity: 'error', rule: 'broken_relationship', linkId: link.id, message: `${link.type} has missing endpoint.` });
      return;
    }
    degree.set(link.source, (degree.get(link.source) || 0) + 1);
    degree.set(link.target, (degree.get(link.target) || 0) + 1);
    if (config.allowedRelationships?.length && !config.allowedRelationships.includes(link.type)) {
      issues.push({ severity: 'warning', rule: 'invalid_relationship_type', linkId: link.id, message: `${link.type} is not registered for ${config.label || config.id}.` });
    }
  });
  degree.forEach((value, id) => { if (value === 0) issues.push({ severity: 'info', rule: 'orphan_node', nodeId: id, message: `${id} has no visible relationships.` }); });
  return { issues, counts: { issues: issues.length, nodes: nodeIds.size, links: (graph.links || []).length } };
}
