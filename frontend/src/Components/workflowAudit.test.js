vi.mock('@siemens/ix-react',()=>import('../ui/ix/ixReact.mock.js'));
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { vi } from 'vitest';
import WorkflowTaskPanel from './WorkflowTaskPanel';
import WorkflowRecoveryActions from './WorkflowRecoveryActions';
import SemanticBridgeJobs from './ontology/SemanticBridgeJobs';
import agenticAPI from '../services/agenticApi';
import { publicationRecoveryScope, setCredentialProfile } from '../services/serviceAuth';

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
  const key=`bridge-workflow:${publicationRecoveryScope()}:ontology:import:[]:0`;
  sessionStorage.setItem(key,'submission-unconfirmed');
  const api={automationStatus:vi.fn().mockResolvedValue({data:{run_id:'wrong',workflow_id:'bridge-validated-automation',status:'completed',traces:[
    {tool_id:'bridge.mapping.preview',status:'completed',result:{kind:'preview',job_id:'p',publication_job_id:'j',ontology_id:'other',import_task_id:'import',candidates:[]}}
  ]}})};
  render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api}/>);
  fireEvent.click(screen.getByText('Recovery: look up a retained workflow'));
  fireEvent.change(screen.getByLabelText('Recover mapping workflow ID'),{target:{value:'wrong'}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect retained mapping workflow'}));
  await screen.findByText('Workflow preview belongs to another source or ontology, or is incomplete.');
  expect(sessionStorage.getItem(key)).toBe('submission-unconfirmed');
  expect(Object.keys(sessionStorage).some(key=>sessionStorage.getItem(key)==='wrong')).toBe(false);
});

test('next mapping partition is sent to the same governed preview', async () => {
  const api={preview:vi.fn().mockResolvedValue({data:{kind:'preview',job_id:'p',publication_job_id:'j',ontology_id:'ontology',import_task_id:'import',candidates:[],partition:{offset:0,total_candidates:2001,next_offset:2000}}})};
  render(<SemanticBridgeJobs ontologyId="ontology" importTaskId="import" api={api}/>);
  fireEvent.click(screen.getByRole('button',{name:'Prepare mappings'}));
  fireEvent.click(await screen.findByRole('button',{name:'Prepare next mapping batch'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare mappings'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Prepare mappings'}));
  await waitFor(()=>expect(api.preview).toHaveBeenCalledTimes(2));
  expect(api.preview.mock.calls[1][4]).toBe(2000);
});


test('server workflow capabilities override stale local fallback including false values', async () => {
  const { mergeWorkflowRuntimeOptions, workflowCatalog } = await import('../workflows/workflowEngine');
  const local = workflowCatalog.find(item => item.id === 'instance.import');
  const [result] = mergeWorkflowRuntimeOptions([local], [{id:local.id, category:'Canonical category',
    inputs:'Registered source', outputs:'Retained evidence, Quality result',
    writes_to_neo4j:false, retains_artifacts:false, status:'artifact_report'}]);
  expect(result).toMatchObject({category:'Canonical category', inputs:'Registered source',
    outputs:['Retained evidence','Quality result'], writes_to_neo4j:false, retains_artifacts:false, status:'available'});
  expect(result.icon).toBe(local.icon);
  expect(result.stages).toEqual(local.stages);
  expect(local.writes_to_neo4j).toBe(true);
});

test('older workflow services preserve compatible display fallback', async () => {
  const { mergeWorkflowRuntimeOptions, workflowCatalog } = await import('../workflows/workflowEngine');
  expect(mergeWorkflowRuntimeOptions(workflowCatalog, [])).toEqual(workflowCatalog);
  const local = workflowCatalog[0];
  const [result] = mergeWorkflowRuntimeOptions([local], [{id:local.id, label:'Server name'}]);
  expect(result.label).toBe('Server name');
  expect(result.outputs).toEqual(local.outputs);
  expect(result.writes_to_neo4j).toBe(local.writes_to_neo4j);
});


test('review workspace links preserve exact source identifiers without executing commands', async () => {
  const {activityWorkspaceLink}=await import('../workflows/workflowEngine');
  const bridge=activityWorkspaceLink('instance.link',{ontologyId:'onto /1',importTaskId:'task&2'});
  const bridgeParams=new URLSearchParams(bridge.split('?')[1]);
  expect(bridge.startsWith('#/ontology?')).toBe(true);
  expect(bridgeParams.get('target')).toBe('onto /1');
  expect(bridgeParams.get('import_task_id')).toBe('task&2');
  const merge=new URLSearchParams(activityWorkspaceLink('ontology.merge',{ontologyId:'a',targetOntologyId:'b'}).split('?')[1]);
  expect(merge.get('mode')).toBe('merge');expect(merge.get('merge_source')).toBe('a');expect(merge.get('target')).toBe('b');
  expect(activityWorkspaceLink('dictionary.generate',{ontologyId:'a'})).toBe('#/registry?view=dictionary&ontology_id=a');
  expect(activityWorkspaceLink('graph.chunk')).toBeNull();
});
