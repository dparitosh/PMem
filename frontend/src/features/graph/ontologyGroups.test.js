import {describe,it,expect} from 'vitest';
import {buildOntologyGroups} from './ontologyGroups';
describe('retained graph grouping',()=>{
 it('keeps ontology versions separate and does not guess from prefixes or IRIs',()=>{
 const result=buildOntologyGroups({nodes:[{elementId:'1',label:'Part',properties:{ontology_id:'a-v1'}},{elementId:'2',label:'Part',ontology_id:'a-v2'},{elementId:'3',iri:'https://a/Part',properties:{prefix:'a'}}]});
 expect(result.groups.map(g=>g.key)).toEqual(['ontology:a-v1','ontology:a-v2','unknown']);
 });
 it('counts directed typed edges, D3 endpoints, and missing endpoints',()=>{
 const result=buildOntologyGroups({nodes:[{elementId:'1',ontology_id:'a'},{elementId:'2',ontology_id:'b'}],links:[{source:{elementId:'1'},target:'2',type:'MAPS_TO'},{source:'2',target:'1',type:'REFERENCE'},{source:'1',target:'1'},{source:'1',target:'absent'}]});
 expect(result.edges).toHaveLength(2);expect(result.groups[0].internalLinks).toBe(1);expect(result.omittedLinks).toBe(1);
 });
 it('uses import provenance without inventing ontology membership',()=>{
 expect(buildOntologyGroups({nodes:[{elementId:'1',properties:{import_task_id:'task'}}]}).groups[0].key).toBe('import:task');
 });
});
