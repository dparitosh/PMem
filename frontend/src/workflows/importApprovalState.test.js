import { isAwaitingImportApproval } from './importPresentation';
test('preview-ready imports wait for approval and active commits do not',()=>{
 expect(isAwaitingImportApproval({status:'ready_for_commit'})).toBe(true);
 for(const status of [{status:'ready_for_commit',committing:true},{status:'ready_for_commit',commitError:'partial write'},{status:'processing'},{status:'completed'},{status:'failed'}]) expect(isAwaitingImportApproval(status)).toBe(false);
});
