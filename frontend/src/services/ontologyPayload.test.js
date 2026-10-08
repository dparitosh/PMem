import {dictionaryPayload} from './ontologyPayload';
import {apiClient,ontologyAPI} from './apiClient';
import {vi} from 'vitest';
test('dictionary contracts preserve property-only and wrapped payloads',()=>{
 const data={properties:{serial:{definition:'Identifier'}}};
 expect(dictionaryPayload(data)).toBe(data);
 expect(dictionaryPayload({data})).toBe(data);
 expect(()=>dictionaryPayload({status:'ok'})).toThrow(/invalid dictionary/);
 expect(()=>dictionaryPayload({entities:[]})).toThrow(/invalid dictionary/);
});
test('taxonomy reasoning and mapping helpers forward cancellation and deadlines',async()=>{
 const get=vi.spyOn(apiClient,'get').mockResolvedValue({data:{}});
 try{
 const options={signal:new AbortController().signal,timeout:30000};
 await ontologyAPI.getTaxonomy('version',options);
 await ontologyAPI.getReasoning('version',options);
 await ontologyAPI.getMappings('version','csv',options);
 expect(get).toHaveBeenCalledTimes(3);
 get.mock.calls.forEach(call=>expect(call[1]).toBe(options));
 }finally{get.mockRestore();}
});

test('inference previews forward cancellation and explicit limits',async()=>{
 const post=vi.spyOn(apiClient,'post').mockResolvedValue({data:{}});
 try{
 const options={signal:new AbortController().signal,timeout:60000};
 const payload={rules:{equivalence:false},limit:250};
 await ontologyAPI.previewInference('version',payload,options);
 expect(post.mock.calls[0].slice(1)).toEqual([payload,options]);
 }finally{post.mockRestore();}
});
