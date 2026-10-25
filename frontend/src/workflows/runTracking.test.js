import {governedRunStatus} from './runTracking';
test('validation failures retain the actionable cause and never claim graph loading',()=>{
 const result=governedRunStatus({run_id:'r',status:'validation_failed',failure:{message:'Unit incompatible'}});
 expect(result.error).toBe(true);expect(result.committed).toBe(false);expect(result.message).toContain('Unit incompatible');
});
test('completed validation is distinguished from a retained publication receipt',()=>{
 const run={run_id:'r',status:'completed',output_manifest:{counts:{normalized_entities:326,normalized_relationships:339}}};
 expect(governedRunStatus(run)).toMatchObject({committed:false,entities:326,relationships:339,stats:{entities_found:326,relationships_found:339}});
 expect(governedRunStatus(run).message).toContain('Graph publication is pending');
 expect(governedRunStatus({...run,output_manifest:{...run.output_manifest,publication:{status:'published',publication_id:'p'}}}).committed).toBe(true);
});

test('queued jobs do not invent zero counts before validation evidence exists',()=>{
 expect(governedRunStatus({run_id:'r',status:'queued'}).stats).toEqual({});
 expect(governedRunStatus({run_id:'r',status:'completed',output_manifest:{counts:{normalized_entities:0,normalized_relationships:0}}}).stats).toEqual({entities_found:0,relationships_found:0});
});
