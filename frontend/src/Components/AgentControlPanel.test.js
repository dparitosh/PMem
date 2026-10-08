import React from 'react';
import { vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AgentControlPanel from './AgentControlPanel';
import { agenticClient } from '../services/agenticApi';
import { getCredentialProfile } from '../services/serviceAuth';

vi.mock('@siemens/ix-react', () => ({ IxButton: props => <button {...props} /> }));
vi.mock('../services/agenticApi', () => ({ agenticClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: vi.fn(key => key === 'GRAPH_READ_TOKEN' ? 'read-fixture' : 'supervisor-fixture') }));

beforeEach(() => { vi.clearAllMocks(); getCredentialProfile.mockImplementation(key => key === 'GRAPH_READ_TOKEN' ? 'read-fixture' : 'supervisor-fixture'); });

test('recovery uses read access and a separate supervisor approval', async () => {
  agenticClient.get.mockResolvedValueOnce({ data: { status: 'failed', traces: [], deadline_at: '2099-01-01T00:00:00Z' } });
  agenticClient.get.mockResolvedValue({ data: { status: 'completed', traces: [] } });
  agenticClient.post.mockResolvedValue({ data: {} });
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'), { target: { value: 'run-fixture' } });
  fireEvent.click(screen.getByText('Inspect / refresh'));
  fireEvent.click(await screen.findByText('Recover remaining steps'));
  await waitFor(() => expect(agenticClient.post).toHaveBeenCalled());
  const [url, payload, options] = agenticClient.post.mock.calls[0];
  expect(url).toMatch(/run-fixture\/recover$/);
  expect(payload.approval_token).toBe('supervisor-fixture');
  expect(options.headers.Authorization).toBe('Bearer read-fixture');
  await screen.findByText('Workflow recovery finished.');
});

test('uncertain writes require receipt evidence before recovery is offered', async () => {
  agenticClient.get.mockResolvedValueOnce({ data: { status: 'failed', pending_step: { mutates: true }, reconciliation_required: true } });
  agenticClient.get.mockResolvedValue({ data: { status: 'recoverable', deadline_at: '2099-01-01T00:00:00Z' } });
  agenticClient.post.mockResolvedValue({ data: {} });
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'), { target: { value: 'run-fixture' } });
  fireEvent.click(screen.getByText('Inspect / refresh'));
  expect(await screen.findByText('Record completed write receipt')).toBeDisabled();
  expect(screen.queryByText('Recover remaining steps')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Downstream verification evidence'), { target: { value: 'Verified graph receipt 123' } });
  fireEvent.change(screen.getByLabelText('Completed write result (JSON)'), { target: { value: '{"publication_id":"123"}' } });
  fireEvent.click(screen.getByText('Record completed write receipt'));
  await waitFor(() => expect(agenticClient.post).toHaveBeenCalled());
  expect(agenticClient.post.mock.calls[0][1]).toEqual(expect.objectContaining({ outcome: 'completed', evidence: 'Verified graph receipt 123', result: { publication_id: '123' } }));
  await screen.findByText('Recover remaining steps');
});

test('cancellation cannot be reversed and heartbeat eligibility controls reconciliation', async () => {
  agenticClient.get.mockResolvedValue({data:{status:'running',execution_state:'cancel_requested',allowed_actions:[],
    control:{action:'cancel'},updated_at:'2000-01-01T00:00:00Z',pending_step:{mutates:true},reconcile_allowed:false}});
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'), {target:{value:'run-cancel'}});
  fireEvent.click(screen.getByText('Inspect / refresh'));
  await screen.findByText(/Run status: cancel_requested/);
  expect(screen.getByText('pause')).toBeDisabled();
  expect(screen.getByText('resume')).toBeDisabled();
  expect(screen.getByText('cancel')).toBeDisabled();
  expect(screen.queryByText('Record completed write receipt')).toBeNull();
});

test('standalone handoff never treats an agent run as a controllable workflow', async () => {
  render(<AgentControlPanel />);
  act(() => window.dispatchEvent(new CustomEvent('depo:inspect-agent-run',{detail:{run_id:'agent-run',status:'completed'}})));
  expect(screen.getByText(/Standalone execution: agent-run/)).toBeVisible();
  expect(screen.getByText('Inspect / refresh')).toBeEnabled();
  expect(screen.getByText('pause')).toBeDisabled();
  expect(agenticClient.get).not.toHaveBeenCalled();
});

test('selected workflow refreshes automatically and shows the acknowledged pause', async () => {
  vi.useFakeTimers();
  try {
    agenticClient.get.mockResolvedValueOnce({data:{status:'running',allowed_actions:['pause','cancel']}})
      .mockResolvedValue({data:{status:'running',execution_state:'paused',allowed_actions:['resume','cancel'],control:{action:'pause',acknowledged_at:'boundary'}}});
    render(<AgentControlPanel />);
    fireEvent.change(screen.getByLabelText('Workflow run ID'), {target:{value:'run-live'}});
    await act(async () => fireEvent.click(screen.getByText('Inspect / refresh')));
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByText(/Run status: paused/)).toBeVisible();
    expect(screen.getByText('pause')).toBeDisabled();
    expect(screen.getByText('resume')).toBeEnabled();
  } finally { vi.useRealTimers(); }
});

test('automatic receipt verification does not require invented evidence or result JSON', async () => {
  agenticClient.get.mockResolvedValueOnce({data:{status:'failed',pending_step:{tool_id:'data.product.publish',mutates:true},reconcile_allowed:true}})
    .mockResolvedValue({data:{status:'recoverable',deadline_at:'2099-01-01T00:00:00Z'}});
  agenticClient.post.mockResolvedValue({data:{status:'recoverable'}});
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'),{target:{value:'run-receipt'}});
  fireEvent.click(screen.getByText('Inspect / refresh'));
  fireEvent.click(await screen.findByText('Verify downstream receipt automatically'));
  await screen.findByText('Reconciliation evidence recorded.');
  expect(agenticClient.post.mock.calls[0][0]).toMatch(/run-receipt\/reconcile-receipt$/);
});

test('revocation requires a reviewed plan and explicit reason, then resets on run change', async () => {
  agenticClient.get.mockResolvedValueOnce({data:{status:'failed',traces:[]}})
    .mockResolvedValueOnce({data:{actions:[{sequence:1,product_version:'quality:1.0.0',effect:'Revoke lifecycle'}],unsupported:[]}});
  agenticClient.post.mockResolvedValue({data:{status:'completed'}});
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'),{target:{value:'run-revoke'}});
  fireEvent.click(screen.getByText('Inspect / refresh'));
  fireEvent.click(await screen.findByText('Review reversible operations'));
  expect(await screen.findByText('Approve revocation of quality:1.0.0')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Compensation reason'),{target:{value:'Withdraw obsolete evidence'}});
  fireEvent.click(screen.getByText('Approve revocation of quality:1.0.0'));
  await screen.findByText(/Compensation for step 1: completed/);
  expect(agenticClient.post.mock.calls[0][0]).toMatch(/run-revoke\/compensate$/);
  expect(agenticClient.post.mock.calls[0][1]).toEqual(expect.objectContaining({sequence:1,reason:'Withdraw obsolete evidence',approval_token:'supervisor-fixture'}));
  fireEvent.change(screen.getByLabelText('Workflow run ID'),{target:{value:'other-run'}});
  expect(screen.queryByText('Approve revocation of quality:1.0.0')).toBeNull();
});


test('capability verification displays independent results and clears on credential changes', async () => {
  agenticClient.post.mockResolvedValue({data:{model:'fixture-model',generation:'verified',structured_outputs:'verified',native_tool_calling:'verification_failed'}});
  render(<AgentControlPanel />);
  fireEvent.click(screen.getByText('Verify Ollama capabilities'));
  await screen.findByText(/Native tool calling: verification_failed/);
  expect(agenticClient.post.mock.calls[0][0]).toMatch(/llm\/probe$/);
  expect(agenticClient.post.mock.calls[0][1].approval_token).toBe('supervisor-fixture');
  act(() => window.dispatchEvent(new Event('depo:credentials-cleared')));
  expect(screen.queryByText(/Capability model: fixture-model/)).toBeNull();
});

test('queued recovery does not claim execution is finished', async () => {
  agenticClient.get.mockResolvedValueOnce({data:{status:'failed',recover_allowed:true,deadline_at:'2099-01-01T00:00:00Z'}})
    .mockResolvedValue({data:{status:'queued',execution_mode:'worker',deadline_at:'2099-01-01T00:00:00Z'}});
  agenticClient.post.mockResolvedValue({data:{status:'queued'}});
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'),{target:{value:'run-queued'}});
  fireEvent.click(screen.getByText('Inspect / refresh'));
  fireEvent.click(await screen.findByText('Recover remaining steps'));
  await screen.findByText('Workflow recovery accepted. Current status: queued.');
  expect(screen.queryByText('Workflow recovery finished.')).toBeNull();
});

test('product receipt verification requires read access instead of forwarding the supervisor token', async () => {
  getCredentialProfile.mockImplementation(key => key === 'GRAPH_READ_TOKEN' ? '' : 'supervisor-fixture');
  agenticClient.get.mockResolvedValue({data:{status:'failed',pending_step:{tool_id:'data.product.publish',mutates:true},reconcile_allowed:true}});
  render(<AgentControlPanel />);
  fireEvent.change(screen.getByLabelText('Workflow run ID'),{target:{value:'run-receipt'}});
  fireEvent.click(screen.getByText('Inspect / refresh'));
  fireEvent.click(await screen.findByText('Verify downstream receipt automatically'));
  await screen.findByText('Connect graph read access before verifying a product publication receipt.');
  expect(agenticClient.post).not.toHaveBeenCalled();
});

test('standalone run selection fetches details and polls without workflow credentials or controls', async () => {
  vi.useFakeTimers();
  try {
    agenticClient.get.mockImplementation(url => Promise.resolve({data:url.includes('observability/runs') ? {runs:[{run_id:'agent-live',operation:'tool',status:'running'}]} : url.includes('?limit=50') ? {runs:[]} : {run_id:'agent-live',status:'running',tool_spans:[{tool_id:'read'}]}}));
    render(<AgentControlPanel />);
    await act(async () => fireEvent.click(screen.getByText('Load recent runs')));
    await act(async () => fireEvent.change(screen.getByLabelText('Recent executions'),{target:{value:'0'}}));
    expect(agenticClient.get.mock.calls.at(-1)[0]).toMatch(/\/runs\/agent-live$/);
    expect(agenticClient.get.mock.calls.at(-1)[1].headers).toEqual({});
    expect(screen.getByText('Standalone execution details')).toBeVisible();
    expect(screen.getByText('pause')).toBeDisabled();
    agenticClient.get.mockResolvedValue({data:{run_id:'agent-live',status:'completed'}});
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByText(/Run status: completed/)).toBeVisible();
    const count=agenticClient.get.mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(6000));
    expect(agenticClient.get.mock.calls.length).toBe(count);
  } finally {vi.useRealTimers();}
});


test('completed workflow handoff stops automatic polling', async () => {
  vi.useFakeTimers();
  try {
    render(<AgentControlPanel />);
    act(() => window.dispatchEvent(new CustomEvent('depo:inspect-agent-run', {detail:{run_id:'finished-run',execution_kind:'workflow',status:'completed',traces:[]}})));
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(agenticClient.get).not.toHaveBeenCalled();
  } finally { vi.useRealTimers(); }
});
