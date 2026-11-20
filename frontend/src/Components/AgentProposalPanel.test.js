import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import AgentProposalPanel from './AgentProposalPanel';
import { agenticClient } from '../services/agenticApi';
import { registerServiceContract, clearServiceContracts } from '../services/serviceContractRegistry';
import { config } from '../config';
vi.mock('../services/agenticApi', () => ({ agenticClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'supervisor', wasBrowserSessionExpired: () => false }));
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); clearServiceContracts(); });
afterEach(() => clearServiceContracts());

test('discovered approver requirement is enforced before execution', async () => {
  registerServiceContract('agentic', config.semanticServiceUrls.agentic, {openapi:'3.0.3',paths:{'/api/v1/runs':{post:{'x-depo-authorization':{approval_fields:['approved_by','approval_token'],required_fields_in_token_mode:['approved_by'],credential_profiles:['AGENTIC_APPROVAL_TOKEN']}}}}});
  agenticClient.get.mockResolvedValue({data:{command:{agent_id:'ontology-governor',tool_id:'ontology.register',inputs:{}},requires_approval:false}});
  render(<AgentProposalPanel />);
  fireEvent.change(screen.getByLabelText('Saved recommendation ID'), {target:{value:'saved-contract'}});
  fireEvent.click(screen.getByText('Load saved recommendation'));
  await screen.findByText('Proposed tool: ontology.register');
  fireEvent.click(screen.getByRole('checkbox'));
  expect(screen.getByText('Execute reviewed recommendation')).toBeEnabled();
  expect(screen.queryByLabelText('Recommendation steward')).toBeNull();
  expect(agenticClient.post).not.toHaveBeenCalled();
  agenticClient.get.mockResolvedValueOnce({data:{actor:'reviewer'}});
  agenticClient.post.mockResolvedValue({data:{run_id:'contract-run',status:'completed'}});
  fireEvent.click(screen.getByText('Execute reviewed recommendation'));
  await screen.findByText('Execution completed. Agent run: contract-run');
  expect(agenticClient.post.mock.calls[0][1].approved_by).toBe('reviewer');
});

test('running execution is not called completed and inspection navigates with a minimal bookmark', async () => {
  agenticClient.get.mockResolvedValue({data:{command:{agent_id:'ontology-governor',tool_id:'ontology.register',inputs:{}},requires_approval:false}});
  agenticClient.post.mockResolvedValue({data:{run_id:'running-one',status:'running',execution_kind:'workflow',result:{private:'not persisted'}}});
  render(<AgentProposalPanel />);
  fireEvent.change(screen.getByLabelText('Saved recommendation ID'), {target:{value:'saved-running'}});
  fireEvent.click(screen.getByText('Load saved recommendation'));
  await screen.findByText('Proposed tool: ontology.register');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Execute reviewed recommendation'));
  await screen.findByText(/Execution running\. Workflow run: running-one/);
  fireEvent.click(screen.getByText('Inspect workflow execution'));
  expect(window.location.hash).toBe('#/admin');
  expect(JSON.parse(sessionStorage.getItem('depo:inspect-agent-run'))).toEqual({run_id:'running-one',status:'running',execution_kind:'workflow'});
  sessionStorage.removeItem('depo:inspect-agent-run');
});

test('failed suggestion exposes its saved prompt for reload', async () => {
  agenticClient.get.mockResolvedValue({data:{agents:[{id:'ontology-governor'}]}});
  agenticClient.post.mockRejectedValue({response:{data:{detail:{message:'Recommendation failed',recommendation_id:'failed-prompt-1'}}}});
  render(<AgentProposalPanel />);
  fireEvent.click(screen.getByText('Load agents'));
  await screen.findByText('ontology-governor');
  fireEvent.change(screen.getByLabelText('Recommendation task'), {target:{value:'Review terms'}});
  fireEvent.click(screen.getByText('Get recommendation'));
  await screen.findByText('Recommendation failed');
  expect(screen.getByLabelText('Saved recommendation ID')).toHaveValue('failed-prompt-1');
  expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
});

test('failed recommendation retains readable prompts without execution controls', async () => {
  agenticClient.get.mockResolvedValue({data:{status:'failed',agent_id:'ontology-governor',execution:'not_executable',failure_status:'timeout',prompt_details:{system_prompt:'Review evidence only',user_request:'Map the terms'}}});
  render(<AgentProposalPanel />);
  fireEvent.change(screen.getByLabelText('Saved recommendation ID'), {target:{value:'failed-1'}});
  fireEvent.click(screen.getByText('Load saved recommendation'));
  expect(await screen.findByText(/Recommendation failed \(timeout\)/)).toBeInTheDocument();
  expect(screen.getByText('Review evidence only')).toBeInTheDocument();
  expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();
});
test('saved recommendation reload requires a fresh review and displays its owner agent', async () => {
  agenticClient.get.mockResolvedValueOnce({data:{recommendation_id:'saved-1',requires_approval:true,
    command:{agent_id:'ontology-governor',tool_id:'bridge.mapping.preview',inputs:{ontology_id:'parts'}}}});
  render(<AgentProposalPanel />);
  fireEvent.change(screen.getByLabelText('Saved recommendation ID'), {target:{value:'saved-1'}});
  fireEvent.click(screen.getByText('Load saved recommendation'));
  await screen.findByText('Proposed tool: bridge.mapping.preview');
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByText('Execute reviewed recommendation')).toBeDisabled();
  expect(screen.getByLabelText('Recommendation agent')).toHaveValue('ontology-governor');
  expect(agenticClient.post).not.toHaveBeenCalled();
});
test('recommendation requires explicit review and approval before execution', async () => {
  agenticClient.get.mockResolvedValue({data:{agents:[{id:'ontology-governor',name:'Ontology Governor'}]}});
  agenticClient.post.mockResolvedValueOnce({data:{requires_approval:true,command:{agent_id:'ontology-governor',tool_id:'bridge.mapping.preview',inputs:{ontology_id:'parts'}}}});
  render(<AgentProposalPanel />);
  fireEvent.click(screen.getByText('Load agents'));
  await screen.findByText('Ontology Governor');
  fireEvent.change(screen.getByLabelText('Recommendation task'), {target:{value:'Review parts mapping'}});
  fireEvent.click(screen.getByText('Get recommendation'));
  await screen.findByText('Proposed tool: bridge.mapping.preview');
  expect(screen.getByText('Execute reviewed recommendation')).toBeDisabled();
  expect(agenticClient.post).toHaveBeenCalledTimes(1);
  agenticClient.get.mockResolvedValueOnce({data:{actor:'reviewer'}});
  fireEvent.click(screen.getByRole('checkbox'));
  agenticClient.post.mockResolvedValueOnce({data:{run_id:'executed-run',status:'completed'}});
  fireEvent.click(screen.getByText('Execute reviewed recommendation'));
  await screen.findByText('Execution completed. Agent run: executed-run');
  expect(agenticClient.post.mock.calls[1][1]).toEqual(expect.objectContaining({approved_by:'reviewer',approval_token:'supervisor'}));
  expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
});

test('malformed recommendations cannot expose executable controls', async () => {
  agenticClient.get.mockResolvedValue({data:{agents:[{id:'ontology-governor'}]}});
  agenticClient.post.mockResolvedValue({data:{command:{agent_id:'ontology-governor',tool_id:'bridge.mapping.preview'}}});
  render(<AgentProposalPanel />);
  fireEvent.click(screen.getByText('Load agents'));
  await screen.findByText('ontology-governor');
  fireEvent.change(screen.getByLabelText('Recommendation task'), {target:{value:'Review mapping'}});
  fireEvent.click(screen.getByText('Get recommendation'));
  await screen.findByText('Invalid agent proposal.');
  expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
});

test('saved recommendation for another selection cannot be executed', async () => {
  agenticClient.get.mockResolvedValue({data:{requires_approval:true, context:{page:'data-flow',job_id:'old'}, command:{agent_id:'data-quality-monitor',tool_id:'pipeline.run',inputs:{}}}});
  render(<AgentProposalPanel agentIds={['data-quality-monitor']} context={{page:'data-flow',job_id:'new'}} />);
  fireEvent.change(screen.getByLabelText('Saved recommendation ID'), {target:{value:'old-recommendation'}});
  fireEvent.click(screen.getByText('Load saved recommendation'));
  await screen.findByText(/belongs to a different page or selection/);
  expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
});

test('session replacement invalidates retained proposal and review consent',async()=>{
 agenticClient.get.mockResolvedValue({data:{command:{agent_id:'graph-analyst',tool_id:'graph.read',inputs:{}},requires_approval:false}});
 render(<AgentProposalPanel/>);
 fireEvent.change(screen.getByLabelText('Saved recommendation ID'),{target:{value:'saved'}});
 fireEvent.click(screen.getByText('Load saved recommendation'));
 await screen.findByText('Proposed tool: graph.read');
 fireEvent.click(screen.getByRole('checkbox'));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 expect(screen.queryByText('Proposed tool: graph.read')).toBeNull();
 expect(screen.queryByText('Execute reviewed recommendation')).toBeNull();
});
test('changing permitted agent list invalidates the loaded selection',async()=>{
 agenticClient.get.mockResolvedValue({data:{agents:[{id:'old-agent',name:'Old agent'}]}});
 const view=render(<AgentProposalPanel agentIds={['old-agent']} context={{page:'data-flow'}}/>);
 fireEvent.click(screen.getByText('Load agents'));
 await screen.findByRole('option',{name:'Old agent'});
 view.rerender(<AgentProposalPanel agentIds={['new-agent']} context={{page:'data-flow'}}/>);
 expect(screen.queryByRole('option',{name:'Old agent'})).toBeNull();
 expect(screen.getByLabelText('Recommendation agent')).toHaveValue('');
});

test('business action summary is primary and technical payload remains available under details',async()=>{
 agenticClient.get.mockResolvedValue({data:{command:{agent_id:'graph-analyst',tool_id:'graph.read',inputs:{node_id:'part-1'}},requires_approval:false,action_summary:{title:'Review component dependencies',description:'Inspect recorded engineering links.',mutates:false}}});
 render(<AgentProposalPanel/>);
 fireEvent.change(screen.getByLabelText('Saved recommendation ID'),{target:{value:'business-review'}});
 fireEvent.click(screen.getByText('Load saved recommendation'));
 expect(await screen.findByRole('heading',{name:'Review component dependencies'})).toBeVisible();
 expect(screen.getByText('Inspect recorded engineering links.')).toBeVisible();
 expect(screen.getByText('Proposed tool: graph.read')).not.toBeVisible();
 expect(screen.getByText('Technical review details')).toBeVisible();
});

test('unverified credential identity cannot execute a reviewed agent proposal',async()=>{
 agenticClient.get.mockResolvedValue({data:{command:{agent_id:'ontology-governor',tool_id:'ontology.register',inputs:{}},requires_approval:true}});
 render(<AgentProposalPanel/>);
 fireEvent.change(screen.getByLabelText('Saved recommendation ID'),{target:{value:'identity-check'}});
 fireEvent.click(screen.getByText('Load saved recommendation'));
 await screen.findByText('Proposed tool: ontology.register');
 fireEvent.click(screen.getByRole('checkbox'));
 agenticClient.get.mockResolvedValueOnce({data:{actor:''}});
 fireEvent.click(screen.getByText('Execute reviewed recommendation'));
 expect(await screen.findByText('Approval identity could not be verified. No action was submitted.')).toBeVisible();
 expect(agenticClient.post).not.toHaveBeenCalled();
});
