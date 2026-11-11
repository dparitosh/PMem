import {recommendationIdentity} from './recommendationScope';

test('identity is placed outside the validated ontology scope',()=>{
 expect(recommendationIdentity({node_id:'revision-b',ontology_prefix:'parts'})).toEqual({node_id:'revision-b',scope:{ontology_prefix:'parts'}});
 expect(recommendationIdentity({element_id:'legacy'})).toEqual({node_id:'legacy'});
});

test('unsupported scope cannot silently broaden to the whole graph',()=>{
 expect(()=>recommendationIdentity({ontology_ids:['one','two']})).toThrow(/ontology_id/);
 expect(()=>recommendationIdentity({namespaces:['one']})).toThrow(/ontology_id/);
});

test('empty scope remains supported and invalid identity is rejected',()=>{
 expect(recommendationIdentity({})).toEqual({});
 expect(()=>recommendationIdentity({node_id:[]})).toThrow(/Invalid/);
});
