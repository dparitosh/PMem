import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReadGoalPanel from './ReadGoalPanel';
import { agenticClient } from '../services/agenticApi';

vi.mock('../services/agenticApi', () => ({agenticClient: {post: vi.fn(), get: vi.fn()}}));
vi.mock('../config', () => ({config:{},buildSemanticServiceUrl: (_, path) => path}));
vi.mock('../utils/apiErrorMessage', () => ({apiErrorMessage: e => e.message}));

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

test('runs a selected read goal and exposes the plan, failure and cited result', async () => {
  const result = {run_id:'goal-test', goal:'Inspect motor', agent_id:'reviewer', status:'completed', decisions:4, max_decisions:8,
    memory_backend:'postgresql', deadline_at:'2099-01-01', plans:[{revision:1,subtasks:['Inspect retained ontology']}],
    observations:[{id:'observation-2',tool_id:'read.first',status:'failed',error_code:'dependency_unavailable',error_message:'Service unavailable'},
      {id:'observation-3',tool_id:'read.other',status:'completed',result:{iri:'urn:Motor'}}],
    result:{summary:'Motor evidence found',evidence_steps:['observation-3']}};
  agenticClient.post.mockResolvedValue({data:result});
  render(<ReadGoalPanel agent="reviewer" task="Inspect motor" context={{ontology_id:'selected'}} />);
  fireEvent.click(screen.getByRole('button',{name:'Start read-only investigation'}));
  await screen.findByText('Motor evidence found');
  expect(agenticClient.post).toHaveBeenCalledWith('/api/v1/agents/reviewer/goals',
    expect.objectContaining({task:'Inspect motor',context:expect.objectContaining({ontology_id:'selected'}),submission_id:expect.any(String)}),expect.anything());
  expect(screen.getByText('Inspect retained ontology')).toBeInTheDocument();
  expect(screen.getByText(/Retained for the next planning decision/)).toBeInTheDocument();
  expect(screen.getByText(/Evidence: observation-3/)).toBeInTheDocument();
});

test('reopens a retained goal and clears its view when credentials change', async () => {
  sessionStorage.setItem('depo:read-goal','goal-existing');
  agenticClient.get.mockResolvedValue({data:{run_id:'goal-existing',goal:'Retained work',status:'completed',plans:[],observations:[]}});
  render(<ReadGoalPanel agent="reviewer" task="Other task" storageKey="depo:read-goal" />);
  await screen.findByText('Retained work');
  fireEvent(window, new Event('depo:credentials-cleared'));
  await waitFor(() => expect(screen.queryByText('Retained work')).not.toBeInTheDocument());
  expect(sessionStorage.getItem('depo:read-goal')).toBeNull();
});


test('cancels an active read goal and retains the visible plan', async () => {
  const running = {run_id:'goal-active',goal:'Inspect motor',status:'running',plans:[{revision:1,subtasks:['Inspect']}],observations:[]};
  agenticClient.post.mockResolvedValueOnce({data:running}).mockResolvedValueOnce({data:{...running,status:'cancelled'}});
  agenticClient.get.mockResolvedValue({data:running});
  render(<ReadGoalPanel agent="reviewer" task="Inspect motor" />);
  fireEvent.click(screen.getByRole('button',{name:'Start read-only investigation'}));
  const cancel = await screen.findByRole('button',{name:'Cancel investigation'});
  await waitFor(() => expect(cancel).toBeEnabled());
  fireEvent.click(cancel);
  await screen.findByText(/Status: cancelled/);
  expect(screen.getByText('Inspect')).toBeInTheDocument();
  expect(agenticClient.post).toHaveBeenCalledWith('/api/v1/goals/goal-active/cancel',{},expect.anything());
});

test('a lost response recovers the same submission even after navigation', async () => {
  agenticClient.post.mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({data:{run_id:'goal-original',status:'completed',goal:'Original work'}});
  const first=render(<ReadGoalPanel agent="reviewer" task="Inspect motor" context={{page:'graph',ontology_id:'selected'}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Start read-only investigation'}));
  await screen.findByRole('button',{name:'Recover submitted investigation'});
  const submission=agenticClient.post.mock.calls[0][1].submission_id;
  first.unmount();
  render(<ReadGoalPanel agent="reviewer" task="Inspect motor" context={{page:'graph',ontology_id:'selected'}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Recover submitted investigation'}));
  expect(await screen.findByText('Original work')).toBeVisible();
  expect(agenticClient.post.mock.calls[1][1].submission_id).toBe(submission);
});

test('changing the selected source clears the previous task view', async () => {
  agenticClient.post.mockResolvedValue({data:{run_id:'goal-original',status:'completed',goal:'Original work'}});
  const view=render(<ReadGoalPanel agent="reviewer" task="Inspect" context={{page:'graph',ontology_id:'first'}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Start read-only investigation'}));
  await screen.findByText('Original work');
  view.rerender(<ReadGoalPanel agent="reviewer" task="Inspect" context={{page:'graph',ontology_id:'second'}}/>);
  await waitFor(()=>expect(screen.queryByText('Original work')).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:'Start read-only investigation'})).toBeEnabled();
});

test('poll cleanup does not abort cancellation and late reads cannot overwrite it', async () => {
  let resolveRead, resolveCancel;
  const running = {run_id:'goal-race',goal:'Inspect',status:'running',plans:[],observations:[]};
  agenticClient.get.mockImplementation(() => new Promise(resolve => { resolveRead = resolve; }));
  agenticClient.post.mockImplementation(() => new Promise(resolve => { resolveCancel = resolve; }));
  render(<ReadGoalPanel agent="reviewer" task="Inspect" initialRunId="goal-race" />);
  await waitFor(() => expect(agenticClient.get).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button',{name:'Cancel investigation'}));
  const signal = agenticClient.post.mock.calls[0][2].signal;
  await waitFor(() => expect(screen.getByRole('button',{name:'Cancel investigation'})).toBeDisabled());
  expect(signal.aborted).toBe(false);
  resolveRead({data:running});
  resolveCancel({data:{...running,status:'cancelled'}});
  await screen.findByText(/Status: cancelled/);
  expect(signal.aborted).toBe(false);
});

test('rejects cancellation results for a different retained goal', async () => {
  agenticClient.get.mockImplementation(() => new Promise(() => {}));
  agenticClient.post.mockResolvedValue({data:{run_id:'goal-other',status:'cancelled',goal:'Other user work'}});
  render(<ReadGoalPanel agent="reviewer" task="Inspect" initialRunId="goal-original" />);
  fireEvent.click(screen.getByRole('button',{name:'Cancel investigation'}));
  await screen.findByRole('alert');
  expect(screen.queryByText('Other user work')).not.toBeInTheDocument();
});
