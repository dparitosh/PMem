import {searchLoadedGraph,graphValueMatches} from './universalGraphSearch';
const nodes=[{elementId:'a',label:'Bolt',properties:{material:'Titanium',approved:false,count:0}},{elementId:'b',label:'Assembly'}];
const links=[{source:'a',target:'b',type:'PART_OF',properties:{position:'Front'}}];
test.each(['titanium','material','false','0','part_of','position','front'])('universal loaded search finds %s with connected endpoints',query=>{
 const result=searchLoadedGraph({nodes,links},query);
 expect(result.nodes.map(node=>node.elementId)).toEqual(['a','b']);
 expect(result.links).toHaveLength(1);
});
test('private values and unrelated objects do not become matches',()=>{
 expect(graphValueMatches({api_key:'hidden'},'hidden')).toBe(false);
 expect(searchLoadedGraph({nodes,links},'unrelated').nodes).toHaveLength(0);
});
test('simulation coordinates are excluded while engineering coordinate properties remain searchable',()=>{
 const data={nodes:[{elementId:'part',label:'Part',x:12345,properties:{x:67890}}],links:[]};
 expect(searchLoadedGraph(data,'12345').nodes).toHaveLength(0);
 expect(searchLoadedGraph(data,'67890').nodes).toHaveLength(1);
});

import {normalizeSearchTerm} from './graphUtils';
test('non-English values remain searchable',()=>{expect(normalizeSearchTerm('  測定  ')).toBe('測定');expect(graphValueMatches({name:'測定'},'測定')).toBe(true);});
