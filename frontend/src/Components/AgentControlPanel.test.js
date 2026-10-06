import React from 'react';
import { vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AgentControlPanel from './AgentControlPanel';
import { agenticClient } from '../services/agenticApi';

vi.mock('@siemens/ix-react', () => ({ IxButton: props => <button {...props} /> }));
vi.mock('../services/agenticApi', () => ({ agenticClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: key => key === 'GRAPH_READ_TOKEN' ? 'read-fixture' : 'supervisor-fixture' }));

beforeEach(() => vi.clearAllMocks());

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
