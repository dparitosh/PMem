import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { vi } from 'vitest';
import WorkflowTaskPanel from './WorkflowTaskPanel';
import WorkflowRecoveryActions from './WorkflowRecoveryActions';
import SemanticBridgeJobs from './ontology/SemanticBridgeJobs';
import agenticAPI from '../services/agenticApi';
import { setCredentialProfile } from '../services/serviceAuth';

beforeEach(() => {
  sessionStorage.clear();
  setCredentialProfile('GRAPH_READ_TOKEN','reader');
  setCredentialProfile('AGENTIC_APPROVAL_TOKEN','supervisor');
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

test('confirmed submission rejection permits retry without an invented workflow ID', async () => {
  const start = vi.spyOn(agenticAPI,'runWorkflow').mockRejectedValue({response:{status:422,headers:{}}});
  render(<WorkflowTaskPanel workflowId="merge" inputs={{}} label="Merge" />);
  fireEvent.click(screen.getByRole('button',{name:'Merge'}));
  await screen.findByText('Task was not accepted. Check access and inputs, then retry.');
  expect(screen.getByRole('button',{name:'Merge'})).toBeEnabled();
  expect(screen.queryByLabelText('Recover workflow ID')).toBeNull();
  expect(Object.values(sessionStorage)).not.toContain('submission-unconfirmed');
  expect(start).toHaveBeenCalledTimes(1);
});

test('server run identity takes precedence over an error response', async () => {
  vi.spyOn(agenticAPI,'runWorkflow').mockRejectedValue({response:{status:422,headers:{'x-depo-run-id':'retained'}}});
  vi.spyOn(agenticAPI,'getRun').mockResolvedValue({data:{run_id:'retained',workflow_id:'merge',status:'failed',traces:[]}});
  render(<WorkflowTaskPanel workflowId="merge" inputs={{}} label="Merge" />);
  fireEvent.click(screen.getByRole('button',{name:'Merge'}));
  await screen.findByText(/Workflow retained:/);
  expect(screen.getByRole('button',{name:'Merge'})).toBeDisabled();
});

test('receipt verification requires executor-stop confirmation when requested by the server', async () => {
  const verify = vi.spyOn(agenticAPI,'reconcileWorkflowReceipt').mockResolvedValue({data:{status:'recoverable'}});
  const refresh = vi.fn();
  render(<WorkflowRecoveryActions run={{run_id:'r',reconcile_allowed:true,executor_stop_verification_required:true}} onRefresh={refresh} />);
  const button = screen.getByRole('button',{name:'Verify publication receipt'});
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(button);
  await waitFor(() => expect(refresh).toHaveBeenCalled());
  expect(verify).toHaveBeenCalledWith('r',{approved_by:'workflow-supervisor',approval_token:'supervisor',executor_stopped:true});
});

test('wrong-source recovery result never replaces the retained run bookmark', async () => {
  const api = {
    automate: vi.fn().mockResolvedValue({data:{run_id:'wrong',workflow_id:'bridge-validated-automation',status:'completed',traces:[
      {tool_id:'bridge.mapping.preview',status:'completed',result:{kind:'preview',job_id:'p',publication_job_id:'j',ontology_id:'other',import_task_id:'import',candidates:[]}}
    ]}})
  };
  render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api} />);
  fireEvent.click(screen.getByRole('button',{name:'Run automated mapping and publish'}));
  await screen.findByText('Workflow preview belongs to another source or ontology, or is incomplete.');
  expect(Object.keys(sessionStorage).some(key => sessionStorage.getItem(key) === 'wrong')).toBe(false);
});

test('next mapping partition is sent to the same governed workflow', async () => {
  const api = {automate:vi.fn().mockResolvedValue({data:{run_id:'first',status:'completed',traces:[
    {tool_id:'bridge.mapping.preview',status:'completed',result:{kind:'preview',job_id:'p',publication_job_id:'j',ontology_id:'ontology',import_task_id:'import',candidates:[],partition:{offset:0,total_candidates:2001,next_offset:2000}}},
    {tool_id:'bridge.mapping.publish_automatic',status:'completed',result:{status:'held'}}
  ]}})};
  render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api} />);
  fireEvent.click(screen.getByRole('button',{name:'Run automated mapping and publish'}));
  fireEvent.click(await screen.findByRole('button',{name:'Prepare next mapping batch'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Run automated mapping and publish'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Run automated mapping and publish'}));
  await waitFor(() => expect(api.automate).toHaveBeenCalledTimes(2));
  expect(api.automate.mock.calls[1][4]).toBe(2000);
});
