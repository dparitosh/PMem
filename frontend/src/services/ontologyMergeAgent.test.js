import { vi } from 'vitest';
vi.mock('./agenticApi', () => ({ default: { runAgent: vi.fn() } }));
vi.mock('./serviceAuth', () => ({ getCredentialProfile: vi.fn(() => 'agent-approval') }));
import agenticAPI from './agenticApi';
import { getCredentialProfile } from './serviceAuth';
import { ontologyMergeAgent } from './ontologyMergeAgent';

beforeEach(() => { vi.clearAllMocks(); getCredentialProfile.mockReturnValue('agent-approval'); });
test('bridge preview uses the governor and unwraps its tool result and telemetry', async () => {
  agenticAPI.runAgent.mockResolvedValue({ data: { agent_id: 'ontology-governor', tool_id: 'ontology.merge.preview', run_id: 'run-preview', result: { preview_id: 'reviewed', conflicts: [] } } });
  const preview = await ontologyMergeAgent.preview(['one', 'two'], { prefix: 'combined' }, ' steward ');
  expect(agenticAPI.runAgent).toHaveBeenCalledWith('ontology-governor', 'ontology.merge.preview', { source_ontology_ids: ['one', 'two'], prefix: 'combined' }, { approved_by: 'steward', approval_token: 'agent-approval' });
  expect(preview.result.preview_id).toBe('reviewed');
  expect(preview.runId).toBe('run-preview');
});
test('commit requests graph publication of the reviewed merge through the governor', async () => {
  agenticAPI.runAgent.mockResolvedValue({ data: { agent_id: 'ontology-governor', tool_id: 'ontology.merge.apply', run_id: 'run-apply', result: { status: 'merged' } } });
  await ontologyMergeAgent.apply('reviewed', 'steward');
  expect(agenticAPI.runAgent).toHaveBeenCalledWith('ontology-governor', 'ontology.merge.apply', { preview_id: 'reviewed', publish: true }, { approved_by: 'steward', approval_token: 'agent-approval' });
});
test('missing approval prevents dispatch', async () => {
  getCredentialProfile.mockReturnValue('');
  await expect(ontologyMergeAgent.apply('reviewed', 'steward')).rejects.toThrow('governed agent access');
  expect(agenticAPI.runAgent).not.toHaveBeenCalled();
});
