import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import agenticAPI from '../services/agenticApi';
import WorkflowTaskPanel from './WorkflowTaskPanel';
import { setCredentialProfile } from '../services/serviceAuth';
beforeEach(() => setCredentialProfile('GRAPH_READ_TOKEN', 'reader'));

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
  expect(screen.queryByRole('button', {name:'Clear inaccessible run bookmark'})).toBeNull();
  expect(screen.getByRole('button', {name:'Review'})).toBeDisabled();
});

test('governed merge passes delegated authorization and per-step inputs without storing credentials', async () => {
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN', 'governed-secret');
  const start = vi.spyOn(agenticAPI, 'runWorkflow').mockResolvedValue({data:{run_id:'merge-run'}});
  vi.spyOn(agenticAPI, 'getRun').mockResolvedValue({data:{run_id:'merge-run',workflow_id:'ontology-union-automation',status:'completed',traces:[]}});
  const steps = [{source_ontology_ids:['a','b']},{},{}];
  render(<WorkflowTaskPanel workflowId="ontology-union-automation" inputs={{}} stepInputs={steps} governed label="Automatic merge" />);
  fireEvent.click(screen.getByRole('button',{name:'Automatic merge'}));
  await screen.findByText(/Workflow merge-run/);
  expect(start.mock.calls[0][2]).toEqual({approved_by:'ontology-merge-automation',approval_token:'governed-secret',step_inputs:steps});
  expect(Object.keys(sessionStorage).filter(key => key.startsWith('["depo:task-run"')).join('')).not.toContain('governed-secret');
});

test('uncertain submission blocks a second merge', async () => {
  vi.spyOn(agenticAPI, 'runWorkflow').mockRejectedValue(new Error('response lost'));
  const view = render(<WorkflowTaskPanel workflowId="merge" inputs={{}} label="Merge" />);
  fireEvent.click(screen.getByRole('button',{name:'Merge'}));
  await screen.findByRole('alert');
  expect(screen.getByRole('button',{name:'Merge'})).toBeDisabled();
  view.unmount();
  render(<WorkflowTaskPanel workflowId="merge" inputs={{}} label="Merge" />);
  expect(screen.getByRole('button',{name:'Merge'})).toBeDisabled();
  expect(screen.getByLabelText('Recover workflow ID')).toBeVisible();
});

test('session expiration retains the running task bookmark and prevents another submission', async () => {
  const start = vi.spyOn(agenticAPI,'runWorkflow').mockResolvedValue({data:{run_id:'running-run'}});
  vi.spyOn(agenticAPI,'getRun').mockResolvedValue({data:{run_id:'running-run',workflow_id:'merge',status:'running',traces:[]}});
  render(<WorkflowTaskPanel workflowId="merge" inputs={{}} label="Merge" />);
  fireEvent.click(screen.getByRole('button',{name:'Merge'}));
  await screen.findByText(/Workflow running-run/);
  fireEvent(window,new Event('depo:session-expired'));
  act(() => setCredentialProfile('GRAPH_READ_TOKEN','renewed-reader'));
  expect(screen.getByRole('button',{name:'Merge'})).toBeDisabled();
  expect(Object.keys(sessionStorage).some(key => sessionStorage.getItem(key)==='running-run')).toBe(true);
  expect(start).toHaveBeenCalledTimes(1);
});
