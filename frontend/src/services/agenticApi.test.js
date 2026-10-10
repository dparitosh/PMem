import { applyAgenticAuth, agenticAPI, agenticClient } from './agenticApi';
import { clearServiceAuthToken, setServiceAuthToken } from './serviceAuth';
import { buildSemanticServiceUrl } from '../config';

afterEach(() => clearServiceAuthToken());

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

test('agent execution uses supported route, explicit tool and approval', async () => {
  const post = jest.spyOn(agenticClient, 'post').mockResolvedValue({ data: {} });
  await agenticAPI.runAgent('ontology-governor', 'ontology.merge.apply', { preview_id: 'p' },
    { approved_by: 'reviewer', approval_token: 'approval' }, { signal: 'signal' });
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/v1/runs'),
    { agent_id: 'ontology-governor', tool_id: 'ontology.merge.apply', inputs: { preview_id: 'p' },
      approved_by: 'reviewer', approval_token: 'approval' }, { signal: 'signal' });
  post.mockRestore();
});

test('workflow execution includes per-step inputs and approval', async () => {
  const post = jest.spyOn(agenticClient, 'post').mockResolvedValue({ data: {} });
  const execution = { step_inputs: [{ id: 'first' }], approved_by: 'reviewer', approval_token: 'approval' };
  await agenticAPI.runWorkflow('review', {}, execution);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/v1/workflow-runs'),
    { workflow_id: 'review', inputs: {}, ...execution }, {});
  post.mockRestore();
});
