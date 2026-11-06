import {test,expect,vi} from 'vitest';
import {recoverMergeResult} from './mergeRecovery';
const plan = {preview_id:'plan',applied_result:{status:'merged',preview_id:'plan',ontology:{ontology_id:'union'}}};
const publication = {ontology_id:'union',status:'published',publication_id:'digest',receipt:{ontology_id:'union',status:'published',current:true,publication_id:'digest',resources:10,relationships:20}};
test('recovery verifies the retained publication using only the supplied reader',async()=>{
 const read=vi.fn(async()=>({data:publication}));
 expect(await recoverMergeResult(plan,read)).toMatchObject({publication_status:'published',publication});
 expect(read).toHaveBeenCalledExactlyOnceWith('union');
});
test('unapplied plans do not request a publication or claim completion',async()=>{
 const read=vi.fn();expect(await recoverMergeResult({preview_id:'plan'},read)).toBeNull();expect(read).not.toHaveBeenCalled();
});
test.each([{...publication,ontology_id:'other'},{...publication,receipt:{...publication.receipt,current:false}},{...publication,receipt:{...publication.receipt,publication_id:'wrong'}}])('mismatched or stale receipt cannot become a successful publication',async value=>{
 await expect(recoverMergeResult(plan,async()=>({data:value}))).rejects.toThrow();
});
test('publication in progress remains running rather than a new merge',async()=>{
 expect(await recoverMergeResult(plan,async()=>({data:{ontology_id:'union',status:'publishing'}}))).toMatchObject({publication_status:'running'});
});
