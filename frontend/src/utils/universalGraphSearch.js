import { getLinkEndpointId } from './graphUtils';
const privateKey = /password|secret|token|api.?key|authorization|credential|embedding|vector/i;
const layoutFields = new Set(['x','y','z','vx','vy','vz','fx','fy','fz','index','source','target']);
export function graphValueMatches(value, query, depth = 0) {
  if (depth > 4 || value == null) return false;
  if (typeof value !== 'object') return String(value).toLowerCase().includes(query);
  if (Array.isArray(value)) return value.some(item => graphValueMatches(item, query, depth + 1));
  return Object.entries(value).some(([key,item]) => !privateKey.test(key) &&
    (key.toLowerCase().includes(query) || graphValueMatches(item, query, depth + 1)));
}
export function searchLoadedGraph(data, query, limit = 80) {
  const term = String(query || '').trim().toLowerCase().replace(/\*+$/, '');
  if (!term) return data || {nodes:[],links:[]};
  const nodes=data?.nodes || [], links=data?.links || [];
  const matched = new Set(nodes.filter(node=>graphValueMatches(Object.fromEntries(Object.entries(node).filter(([key])=>!layoutFields.has(key))),term)).slice(0,limit).map(node=>node.elementId));
  const selectedLinks=links.filter(link=>graphValueMatches({type:link.type,label:link.label,properties:link.properties},term) || matched.has(getLinkEndpointId(link.source)) || matched.has(getLinkEndpointId(link.target))).slice(0,limit*4);
  selectedLinks.forEach(link=>{matched.add(getLinkEndpointId(link.source));matched.add(getLinkEndpointId(link.target));});
  const selected=nodes.filter(node=>matched.has(node.elementId)).slice(0,limit*3);
  const ids=new Set(selected.map(node=>node.elementId));
  return {nodes:selected,links:selectedLinks.filter(link=>ids.has(getLinkEndpointId(link.source))&&ids.has(getLinkEndpointId(link.target)))};
}
