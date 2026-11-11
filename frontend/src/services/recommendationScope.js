export function recommendationIdentity(scope = {}) {
  if (!scope || typeof scope !== 'object' || Array.isArray(scope)) throw new Error('Select one ontology scope and graph object.');
  const allowed = new Set(['node_id','element_id','ontology_id','ontology_prefix','prefix']);
  if (Object.keys(scope).some(key => !allowed.has(key))) throw new Error('Use ontology_id or ontology_prefix to scope the recommendation.');
  if (Object.values(scope).some(value => typeof value !== 'string' || value.length > 256)) throw new Error('Invalid recommendation identity or scope.');
  const node = scope.node_id || scope.element_id;
  const selected = Object.fromEntries(['ontology_id','ontology_prefix','prefix'].filter(key => scope[key]).map(key => [key,scope[key]]));
  return {...(node ? {node_id:node} : {}), ...(Object.keys(selected).length ? {scope:selected} : {})};
}
