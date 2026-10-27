import { applyAgenticAuth, agenticAPI, agenticClient } from './agenticApi';
vi.unmock('axios');
import { clearServiceAuthToken, setServiceAuthToken } from './serviceAuth';
import { buildSemanticServiceUrl } from '../config';

afterEach(() => clearServiceAuthToken());

test('execution metadata captures the page without modifying tool inputs',()=>{
 window.location.hash='#/ontology';
 const inputs={ontology_id:'selected'};
 const request=applyAgenticAuth({method:'post',url:buildSemanticServiceUrl('agentic','/api/v1/runs'),data:{tool_id:'review',inputs},headers:{}});
 expect(request.data.page_context).toEqual({page:'ontology'});
 expect(request.data.inputs).toBe(inputs);
 const scoped=applyAgenticAuth({method:'post',url:buildSemanticServiceUrl('agentic','/api/v1/workflow-runs'),data:{page_context:{page:'import',ontology_id:'selected'}},headers:{}});
 expect(scoped.data.page_context).toEqual({page:'import',ontology_id:'selected'});
 window.location.hash='';
});

test('Admin OpenAPI import method returns a local metadata preview', async () => {
  const result = await agenticAPI.importOpenApi({openapi:'3.0.3',paths:{'/health':{get:{summary:'Health'}}}}, 'service.json');
  expect(result.data.title).toBe('service.json');
  expect(result.data.summary.operations).toBe(1);
});

test('a scoped ontology-agent token takes precedence over the app token', () => {
  setServiceAuthToken('app-token');
  const request = { headers: { Authorization: 'Bearer ontology-read-token' } };
  const configured = applyAgenticAuth(request);
  expect(configured.headers.Authorization).toBe('Bearer ontology-read-token');
});

test('the app token is used when a request has no scoped token', () => {
  setServiceAuthToken('app-token');
  const configured = applyAgenticAuth({ headers: {}, method: 'get', url: buildSemanticServiceUrl('agentic', '/api/v1/agents') });
  expect(configured.headers.Authorization).toBe('Bearer app-token');
});

test('reconnect aborts agent requests and ignores old success and rejection responses',async()=>{
 setServiceAuthToken('old-key');
 const request=applyAgenticAuth({headers:{},method:'post',url:buildSemanticServiceUrl('agentic','/api/v1/runs')});
 window.dispatchEvent(new Event('depo:session-replaced'));
 expect(request.signal.aborted).toBe(true);
 const receive=agenticClient.interceptors.response.handlers[0];
 const update=jest.fn(),rejected=jest.fn();
 window.addEventListener('depo:page-task-updated',update);window.addEventListener('depo:access-rejected',rejected);
 try{
  await expect(receive.fulfilled({config:request,data:{run_id:'old-run'}})).rejects.toThrow(/previous credentials/);
  await expect(receive.rejected({config:request,response:{status:403,data:{detail:'Required API key is missing or invalid'}}})).rejects.toThrow(/previous agent request/);
  expect(update).not.toHaveBeenCalled();expect(rejected).not.toHaveBeenCalled();
 }finally{window.removeEventListener('depo:page-task-updated',update);window.removeEventListener('depo:access-rejected',rejected);}
});

test('caller cancellation is preserved by the shared agent request guard',()=>{
 const controller=new AbortController();
 const request=applyAgenticAuth({headers:{},method:'get',url:buildSemanticServiceUrl('agentic','/api/v1/agents'),signal:controller.signal});
 controller.abort();expect(request.signal.aborted).toBe(true);
});

test('agent execution uses supported route, explicit tool and approval', async () => {
  const post = jest.spyOn(agenticClient, 'post').mockResolvedValue({ data: {} });
  await agenticAPI.runAgent('ontology-governor', 'ontology.merge.apply', { preview_id: 'p' },
    { approved_by: 'reviewer', approval_token: 'approval' }, { signal: 'signal' });
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/v1/runs'),
    { agent_id: 'ontology-governor', tool_id: 'ontology.merge.apply', inputs: { preview_id: 'p' },
      approved_by: 'reviewer', approval_token: 'approval' }, { timeout: 3660000, signal: 'signal' });
  post.mockRestore();
});

test('workflow execution includes per-step inputs and approval', async () => {
  const post = jest.spyOn(agenticClient, 'post').mockResolvedValue({ data: {} });
  const execution = { step_inputs: [{ id: 'first' }], approved_by: 'reviewer', approval_token: 'approval' };
  await agenticAPI.runWorkflow('review', {}, execution);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/v1/workflow-runs'),
    { workflow_id: 'review', inputs: {}, ...execution }, { timeout: 3660000 });
  post.mockRestore();
});


test('ontology review waits for slow LLM while preserving caller cancellation', async () => {
  const post = jest.spyOn(agenticClient, 'post').mockResolvedValue({data:{}});
  try {
    await agenticAPI.orchestrateOntology({workflow_id:'qif_ap242_review'}, {signal:'signal'});
    expect(post.mock.calls[0][2].timeout).toBeGreaterThanOrEqual(1200000);
    expect(post.mock.calls[0][2].signal).toBe('signal');
  } finally {post.mockRestore();}
});
