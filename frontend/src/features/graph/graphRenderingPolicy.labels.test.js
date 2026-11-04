import {getRelationshipDisplayName} from './graphRenderingPolicy';

test('published vocabulary label takes precedence over storage relationship type',()=>{
 expect(getRelationshipDisplayName({type:'SEMANTIC_RELATION',business_label:'has manufacturing activity',properties:{predicate:'urn:hasProcess'}})).toBe('has manufacturing activity');
});
test('generic storage edges expose canonical predicate words without inventing ownership',()=>{
 expect(getRelationshipDisplayName({type:'SEMANTIC_RELATION',properties:{predicate:'https://example.org/hasPMI'}})).toBe('has PMI');
 expect(getRelationshipDisplayName({type:'SEMANTIC_RELATION',properties:{predicate:'https://example.org/hasDocument'}})).toBe('has Document');
 expect(getRelationshipDisplayName({type:'SEMANTIC_RELATION',properties:{predicate:'https://example.org/?key=private'}})).toBe('SEMANTIC_RELATION');
 expect(getRelationshipDisplayName({type:'SEMANTIC_RELATION',business_label:'owns',properties:{collapsed:true}})).toBe('Trace Link');
});
