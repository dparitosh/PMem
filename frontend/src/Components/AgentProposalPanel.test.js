import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AgentProposalPanel from './AgentProposalPanel';
import { agenticClient } from '../services/agenticApi';
vi.mock('../services/agenticApi', () => ({ agenticClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../services/serviceAuth', () => ({ getCredentialProfile: () => 'supervisor' }));
beforeEach(() => vi.clearAllMocks());

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
  fireEvent.change(screen.getByLabelText('Recommendation steward'),{target:{value:'reviewer'}});
  fireEvent.click(screen.getByRole('checkbox'));
  agenticClient.post.mockResolvedValueOnce({data:{run_id:'executed-run'}});
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
