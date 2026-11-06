import { vi } from 'vitest';
vi.mock('./agenticApi', () => ({ default: { runAgent: vi.fn() } }));
vi.mock('./serviceAuth', () => ({ getCredentialProfile: vi.fn(() => 'agent-approval') }));
import agenticAPI from './agenticApi';
import { agentToolResult } from './agentToolResult';
import { getCredentialProfile } from './serviceAuth';
import { ontologyMergeAgent, validStewardReport } from './ontologyMergeAgent';

test('partial or failed agent results cannot become reviewed evidence',()=>{
 for(const run of [
   {status:'failed',run_id:'r',result:{}},
   {status:'running',run_id:'r',result:{}},
   {status:'completed',result:{}},
   {status:'completed',run_id:'r',result:[]},
 ]) expect(()=>agentToolResult({data:{agent_id:'ontology-governor',tool_id:'ontology.merge.preview',...run}},'ontology-governor','ontology.merge.preview')).toThrow('incompatible result');
});

beforeEach(() => { vi.clearAllMocks(); getCredentialProfile.mockReturnValue('agent-approval'); });
test('bridge preview uses the governor and unwraps its tool result and telemetry', async () => {
  agenticAPI.runAgent.mockResolvedValue({ data: { agent_id: 'ontology-governor', tool_id: 'ontology.merge.preview', run_id: 'run-preview', result: { preview_id: 'reviewed', conflicts: [] } } });
  const preview = await ontologyMergeAgent.preview(['one', 'two'], { prefix: 'combined' }, ' steward ');
  expect(agenticAPI.runAgent).toHaveBeenCalledWith('ontology-governor', 'ontology.merge.preview', { source_ontology_ids: ['one', 'two'], prefix: 'combined' }, { approved_by: 'steward', approval_token: 'agent-approval' });
  expect(preview.result.preview_id).toBe('reviewed');
  expect(preview.runId).toBe('run-preview');
});
test('commit requests graph publication of the reviewed merge through the governor', async () => {
  agenticAPI.runAgent.mockResolvedValue({ data: { agent_id: 'ontology-governor', tool_id: 'ontology.merge.apply', run_id: 'run-apply', result: { status: 'merged',preview_id:'reviewed',ontology:{ontology_id:'merged'},publication_status:'published',publication:{status:'published',ontology_id:'merged',publication_id:'receipt',receipt:{status:'published',current:true,ontology_id:'merged',publication_id:'receipt',resources:10,relationships:5}} } } });
  await ontologyMergeAgent.apply('reviewed', 'steward');
  expect(agenticAPI.runAgent).toHaveBeenCalledWith('ontology-governor', 'ontology.merge.apply', { preview_id: 'reviewed', publish: true }, { approved_by: 'steward', approval_token: 'agent-approval' });
});

test('publication status alone cannot establish a verified merge', async () => {
  agenticAPI.runAgent.mockResolvedValue({data:{agent_id:'ontology-governor',tool_id:'ontology.merge.apply',run_id:'run',result:{status:'merged',preview_id:'reviewed',ontology:{ontology_id:'merged'},publication_status:'published'}}});
  await expect(ontologyMergeAgent.apply('reviewed','steward')).rejects.toThrow('receipt is unverified');
});
test('missing approval prevents dispatch', async () => {
  getCredentialProfile.mockReturnValue('');
  await expect(ontologyMergeAgent.apply('reviewed', 'steward')).rejects.toThrow('governed agent access');
  expect(agenticAPI.runAgent).not.toHaveBeenCalled();
});

test('queued merge publication retains its job identity without claiming graph completion', async () => {
  agenticAPI.runAgent.mockResolvedValue({data:{agent_id:'ontology-governor',tool_id:'ontology.merge.apply',run_id:'run',result:{
    status:'merged',preview_id:'reviewed',ontology:{ontology_id:'merged'},publication_status:'queued',publication:{status:'queued',ontology_id:'merged',job_id:'job'}
  }}});
  const response = await ontologyMergeAgent.apply('reviewed','steward');
  expect(response.result.publication.job_id).toBe('job');
  expect(response.result.publication_status).toBe('queued');
});


test('the existing Steward evaluates the exact saved Governor plan',async()=>{
 agenticAPI.runAgent.mockResolvedValue({data:{agent_id:'ontology-steward',tool_id:'ontology.merge.evaluate',run_id:'steward-run',result:{preview_id:'saved',governance:approvedReport()}}});
 const result=await ontologyMergeAgent.evaluate('saved','reviewer');
 expect(result.runId).toBe('steward-run');
 expect(agenticAPI.runAgent).toHaveBeenCalledWith('ontology-steward','ontology.merge.evaluate',{preview_id:'saved'},{approved_by:'reviewer',approval_token:'agent-approval'});
 agenticAPI.runAgent.mockResolvedValue({data:{agent_id:'ontology-governor',tool_id:'ontology.merge.evaluate',run_id:'wrong-agent',result:{}}});
 await expect(ontologyMergeAgent.evaluate('saved','reviewer')).rejects.toThrow('incompatible');
});

function approvedReport(){return {
 audit_id:'a'.repeat(64),policy_sha256:'b'.repeat(64),artifact_sha256:'c'.repeat(64),
 profile:'imported_standard',recommended_version_bump:'MINOR',overall_verdict:'APPROVED',
 violations_and_remediations:[],metrics:{findings:0,quarantined_subjects:0},
 coverage:{complete:true,shacl:'retained-result',owl_rl_performed:true}
};}
test('malformed or contradictory approvals cannot unlock publication',()=>{
 expect(validStewardReport(approvedReport())).toBe(true);
 for(const patch of [
  {audit_id:'audit'}, {artifact_sha256:undefined}, {profile:'unknown'},
  {coverage:{complete:false,shacl:'retained-result',owl_rl_performed:true}},
  {coverage:{complete:true,shacl:'pending',owl_rl_performed:true}},
  {coverage:{complete:true,shacl:'retained-result',owl_rl_performed:false}},
  {metrics:{findings:1,quarantined_subjects:1}},
  {violations_and_remediations:[{severity:'BLOCKER',subject_uri:'urn:a',issue_category:'identity',diagnosis:'held',action_taken:'QUARANTINED'}]},
  {violations_and_remediations:[{}]},
 ]) expect(validStewardReport({...approvedReport(),...patch})).toBe(false);
});
test('a valid held report remains readable',()=>{
 expect(validStewardReport({...approvedReport(),overall_verdict:'PENDING_VALIDATION',coverage:{complete:true,shacl:'pending'}})).toBe(true);
});
