// Membership uses explicit retained provenance, never labels, prefixes or IRI guesses.
export function buildOntologyGroups(data = {}) {
  const groups = new Map(), membership = new Map();
  for (const node of data.nodes || []) {
    const p = node.properties || {};
    const ontology = node.ontology_id || p.ontology_id || node.source_ontology || p.source_ontology;
    const task = p.import_id || node.import_id || p.import_task_id || node.import_task_id;
    const key = ontology ? `ontology:${ontology}` : task ? `import:${task}` : 'unknown';
    if (!groups.has(key)) groups.set(key, {key, ontologyId: ontology || null, label: ontology ? String(ontology) : task ? `Import ${task}` : 'Unassigned provenance', nodes: [], internalLinks: 0});
    groups.get(key).nodes.push(node);
    membership.set(String(node.elementId || node.id), key);
  }
  const edges = new Map();
  const endpoint = value => String(typeof value === 'object' ? value?.elementId || value?.id : value);
  let omittedLinks = 0;
  for (const link of data.links || []) {
    const a = membership.get(endpoint(link.source)), b = membership.get(endpoint(link.target));
    if (!a || !b) { omittedLinks++; continue; }
    if (a === b) { groups.get(a).internalLinks++; continue; }
    const type = link.type || link.label || link.properties?.predicate || 'Unspecified relationship';
    const key = JSON.stringify([a,b,type]);
    if (!edges.has(key)) edges.set(key,{source:a,target:b,type,count:0});
    edges.get(key).count++;
  }
  return {groups:[...groups.values()].sort((a,b)=>a.key.localeCompare(b.key)), edges:[...edges.values()], omittedLinks};
}
