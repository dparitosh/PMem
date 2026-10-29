import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import WorkflowRecoveryActions from './WorkflowRecoveryActions';
import agenticAPI from '../services/agenticApi';
import { setCredentialProfile } from '../services/serviceAuth';

afterEach(() => vi.restoreAllMocks());

test('advisory review owner can recover with reader access and no approval credential', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-reader');
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', '');
  const recover = vi.spyOn(agenticAPI, 'recoverWorkflow').mockResolvedValue({ data: {} });
  render(<WorkflowRecoveryActions run={{ run_id: 'review-1', recover_allowed: true, recovery_requires_approval: false }} onRefresh={vi.fn()} />);
  const button = screen.getByRole('button', { name: 'Recover retained workflow' });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() => expect(recover).toHaveBeenCalledWith('review-1', {}));
});

test('publication recovery still requires approval access', () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-reader');
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', '');
  render(<WorkflowRecoveryActions run={{ run_id: 'write-1', recover_allowed: true, recovery_requires_approval: true, reconcile_allowed: true }} onRefresh={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Recover retained workflow' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Verify publication receipt' })).toBeDisabled();
});

test('recovery rejection explains the server reason and retains request identity', async () => {
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', 'fixture-approval');
  vi.spyOn(agenticAPI, 'recoverWorkflow').mockRejectedValue({ response: {
    status: 409, data: { detail: 'The original workflow deadline has expired' },
    headers: { 'x-request-id': 'request-1' },
  } });
  render(<WorkflowRecoveryActions run={{ run_id: 'run-1', recover_allowed: true }} onRefresh={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Recover retained workflow' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('The original workflow deadline has expired Request ID: request-1');
});

test('recovery is single flight and an old run cannot refresh a newly selected run', async () => {
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', 'fixture-approval');
  let finish;
  const recover = vi.spyOn(agenticAPI, 'recoverWorkflow').mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const refresh = vi.fn();
  const view = render(<WorkflowRecoveryActions run={{ run_id: 'run-1', recover_allowed: true }} onRefresh={refresh} />);
  const button = screen.getByRole('button', { name: 'Recover retained workflow' });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(recover).toHaveBeenCalledTimes(1);
  view.rerender(<WorkflowRecoveryActions run={{ run_id: 'run-2', recover_allowed: true }} onRefresh={refresh} />);
  finish({ data: {} });
  await waitFor(() => expect(button).toBeEnabled());
  expect(refresh).not.toHaveBeenCalled();
});
