import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import agenticAPI from '../services/agenticApi';
import WorkflowTaskPanel from './WorkflowTaskPanel';

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });
test('restores a retained workflow without submitting another execution', async () => {
  const start = vi.spyOn(agenticAPI, 'runWorkflow').mockResolvedValue({ data: { run_id: 'run-1' } });
  vi.spyOn(agenticAPI, 'getRun').mockResolvedValue({ data: { run_id: 'run-1', workflow_id: 'review', status: 'completed', traces: [{ result: { evidence: 'retained' } }] } });
  const result = vi.fn();
  const view = render(<WorkflowTaskPanel workflowId="review" inputs={{ ontology_id: 'one' }} label="Review" onResult={result} />);
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  await waitFor(() => expect(result).toHaveBeenCalled());
  view.unmount();
  render(<WorkflowTaskPanel workflowId="review" inputs={{ ontology_id: 'one' }} label="Review" />);
  await screen.findByText(/completed. Results remain/);
  expect(start).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled();
});
test('keeps run identity when status refresh fails and exposes a refresh action', async () => {
  vi.spyOn(agenticAPI, 'runWorkflow').mockResolvedValue({ data: { run_id: 'run-2' } });
  vi.spyOn(agenticAPI, 'getRun').mockRejectedValue(new Error('offline'));
  render(<WorkflowTaskPanel workflowId="review" inputs={{ ontology_id: 'two' }} label="Review" />);
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  await screen.findByRole('alert');
  expect(screen.getByText(/Workflow run-2/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Refresh status' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled();
});

test('malformed action lists cannot crash the panel or deliver results', async () => {
  vi.spyOn(agenticAPI, 'runWorkflow').mockResolvedValue({data:{run_id:'invalid-run'}});
  vi.spyOn(agenticAPI, 'getRun').mockResolvedValue({data:{run_id:'invalid-run',workflow_id:'review',status:'completed',allowed_actions:{pause:true}}});
  const result = vi.fn();
  render(<WorkflowTaskPanel workflowId="review" inputs={{}} label="Review" onResult={result} />);
  fireEvent.click(screen.getByRole('button', {name:'Review'}));
  await screen.findByRole('alert');
  expect(result).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name:'Clear inaccessible run bookmark'})).toBeEnabled();
});
