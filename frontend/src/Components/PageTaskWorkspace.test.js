import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import PageTaskWorkspace from './PageTaskWorkspace';
import api, { agenticClient } from '../services/agenticApi';
import { pageTaskProfiles } from '../services/pageTasks';
import { navigationItems } from '../app/navigation';
vi.mock('../services/agenticApi',()=>({default:{pageTasks:vi.fn(),pageTask:vi.fn(),controlWorkflow:vi.fn()},agenticClient:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../config',()=>({config:{},buildSemanticServiceUrl:(_,path)=>path}));
vi.mock('./AgentProposalPanel',()=>({default:()=> <p>Scoped task controls</p>}));
const row=(kind='workflow')=>({run_id:kind==='goal'?'goal-retained':'retained',kind,title:'Inspect source',status:'paused',agent_id:'reviewer',page_context:{page:'ontology'}});
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();api.pageTasks.mockResolvedValue({data:{page:'ontology',tasks:[row()],has_more:false}});});
const open=()=>fireEvent.click(screen.getByRole('button',{name:/Guided work/}));
afterEach(()=>vi.useRealTimers());

test('an aborted history response cannot create a second polling loop',async()=>{
 vi.useFakeTimers();let resolve;
 const data={data:{page:'ontology',tasks:[],has_more:false}};
 api.pageTasks.mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValue(data);
 render(<PageTaskWorkspace page="ontology"/>);open();
 await act(async()=>{fireEvent(window,new Event('depo:page-task-updated'));});
 await act(async()=>{resolve(data);});
 expect(api.pageTasks).toHaveBeenCalledTimes(2);
 await act(async()=>{vi.advanceTimersByTime(15000);});
 expect(api.pageTasks).toHaveBeenCalledTimes(3);
});
test('every navigation page has journey guidance',()=>{
 expect(Object.keys(pageTaskProfiles).sort()).toEqual(navigationItems.map(item=>item.id).sort());
 for(const profile of Object.values(pageTaskProfiles))expect(profile.steps.length).toBe(3);
});
test('opening history reads the current page and exposes only server allowed controls',async()=>{
 api.pageTask.mockResolvedValue({data:{run_id:'retained',status:'paused',allowed_actions:['resume'],traces:[]}});
 render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));
 expect(await screen.findByRole('button',{name:'Resume workflow'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Cancel workflow'})).not.toBeInTheDocument();
 expect(api.pageTasks).toHaveBeenCalledWith('ontology',0,expect.objectContaining({timeout:15000}));
 expect(api.controlWorkflow).not.toHaveBeenCalled();
});
test('a retained read goal is opened without submitting another execution',async()=>{
 api.pageTasks.mockResolvedValue({data:{page:'ontology',tasks:[row('goal')]}});
 agenticClient.get.mockResolvedValue({data:{run_id:'goal-retained',goal:'Retained conclusion',status:'completed'}});
 render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));
 expect(await screen.findByText('Retained conclusion')).toBeVisible();
 expect(agenticClient.post).not.toHaveBeenCalled();
 expect(screen.queryByRole('button',{name:'Start read-only investigation'})).not.toBeInTheDocument();
});
test('mismatched page history is rejected and credential changes clear the view',async()=>{
 api.pageTasks.mockResolvedValue({data:{page:'graph',tasks:[row()]}});
 render(<PageTaskWorkspace page="ontology"/>);open();
 expect(await screen.findByRole('alert')).toHaveTextContent('incompatible page scope');
 expect(screen.queryByRole('button',{name:'Inspect source'})).not.toBeInTheDocument();
 fireEvent(window,new Event('depo:credentials-cleared'));
 expect(screen.getByRole('button',{name:/Guided work/})).toHaveAttribute('aria-expanded','false');
});
test('detail outage never enables stale workflow controls',async()=>{
 api.pageTask.mockRejectedValue(new Error('Status unavailable'));
 render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));
 await waitFor(()=>expect(api.pageTask).toHaveBeenCalled());
 expect(screen.queryByRole('button',{name:'Resume workflow'})).not.toBeInTheDocument();
 expect(api.controlWorkflow).not.toHaveBeenCalled();
});
test('an uncertain control response requires a new server read before another control',async()=>{
 api.pageTask.mockResolvedValue({data:{run_id:'retained',status:'paused',allowed_actions:['resume']}});
 api.controlWorkflow.mockRejectedValue(new Error('Response lost'));
 render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));
 fireEvent.click(await screen.findByRole('button',{name:'Resume workflow'}));
 await waitFor(()=>expect(api.controlWorkflow).toHaveBeenCalledTimes(1));
 expect(screen.queryByRole('button',{name:'Resume workflow'})).not.toBeInTheDocument();
});

test('session replacement clears task controls and ignores a delayed control acknowledgement',async()=>{
 let resolve;
 api.pageTask.mockResolvedValue({data:{run_id:'retained',status:'paused',allowed_actions:['resume']}});
 api.controlWorkflow.mockImplementation(()=>new Promise(r=>{resolve=r;}));
 render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));
 fireEvent.click(await screen.findByRole('button',{name:'Resume workflow'}));
 fireEvent(window,new Event('depo:session-replaced'));resolve({data:{}});
 await waitFor(()=>expect(screen.getByRole('button',{name:/Guided work/})).toHaveAttribute('aria-expanded','false'));
 open();await screen.findByRole('button',{name:'Inspect source'});
 expect(screen.queryByText(/resume requested/)).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Resume workflow'})).not.toBeInTheDocument();
});

test('pending history is loading, not a successful empty history',async()=>{
 api.pageTasks.mockReturnValue(new Promise(()=>{}));render(<PageTaskWorkspace page="ontology"/>);open();
 expect(screen.getByText('Loading task history…')).toBeVisible();
 expect(screen.queryByText('No retained agent tasks on this page.')).not.toBeInTheDocument();
});

test('changing workspace removes the selected task and its control scope',async()=>{
 api.pageTask.mockResolvedValue({data:{run_id:'retained',status:'paused',allowed_actions:['resume']}});
 const view=render(<PageTaskWorkspace page="ontology"/>);open();
 fireEvent.click(await screen.findByRole('button',{name:'Inspect source'}));await screen.findByRole('button',{name:'Resume workflow'});
 api.pageTasks.mockResolvedValue({data:{page:'catalog',tasks:[],has_more:false}});
 view.rerender(<PageTaskWorkspace page="catalog"/>);
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Resume workflow'})).not.toBeInTheDocument());
 expect(api.controlWorkflow).not.toHaveBeenCalled();
});

test.each(['change-control','data-flow','ontology','catalog','data-products','registry'])('workspace %s explains execution, agent role and delivery independently',async(page)=>{
 api.pageTasks.mockResolvedValue({data:{page,tasks:[],has_more:false}});
 render(<PageTaskWorkspace page={page}/>);open();
 expect(screen.getByRole('region',{name:'Workflow responsibilities'})).toBeVisible();
 await screen.findByText('No retained agent tasks on this page.');
 expect(api.controlWorkflow).not.toHaveBeenCalled();
});

test('rejected access stops history polling until access is verified again',async()=>{
 vi.useFakeTimers();
 api.pageTasks.mockRejectedValueOnce({response:{status:403}}).mockResolvedValue({data:{page:'ontology',tasks:[],has_more:false}});
 render(<PageTaskWorkspace page="ontology"/>);open();
 await act(async()=>{});
 expect(api.pageTasks).toHaveBeenCalledTimes(1);
 await act(async()=>{vi.advanceTimersByTime(60000);});
 expect(api.pageTasks).toHaveBeenCalledTimes(1);
 await act(async()=>{fireEvent(window,new Event('depo:access-verified'));});
 expect(api.pageTasks).toHaveBeenCalledTimes(2);
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('collapsed investigation controls do not initialize agent configuration',async()=>{
 api.pageTasks.mockResolvedValue({data:{page:'registry',tasks:[],has_more:false}});
 render(<PageTaskWorkspace page="registry"/>);open();
 await screen.findByText('No retained agent tasks on this page.');
 expect(screen.queryByText('Scoped task controls')).not.toBeInTheDocument();
 const details=screen.getByText('Start a scoped investigation or reviewed action').closest('details');
 details.open=true;fireEvent(details,new Event('toggle'));
 expect(await screen.findByText('Scoped task controls')).toBeVisible();
});

test('hidden workspaces stop polling and refresh immediately when visible',async()=>{
 vi.useFakeTimers();const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(false);
 try{
  api.pageTasks.mockResolvedValue({data:{page:'ontology',tasks:[],has_more:false}});
  render(<PageTaskWorkspace page="ontology"/>);open();await act(async()=>{});
  hidden.mockReturnValue(true);fireEvent(document,new Event('visibilitychange'));
  await act(async()=>{vi.advanceTimersByTime(60000);});
  expect(api.pageTasks).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(false);await act(async()=>{fireEvent(document,new Event('visibilitychange'));});
  expect(api.pageTasks).toHaveBeenCalledTimes(2);
 }finally{hidden.mockRestore();}
});

test('a transient detail failure recovers by reading without replaying an action',async()=>{
 vi.useFakeTimers();
 api.pageTask.mockRejectedValueOnce(new Error('Temporary connection failure')).mockResolvedValue({data:{run_id:'retained',status:'completed',traces:[]}});
 render(<PageTaskWorkspace page="ontology"/>);open();await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Inspect source'}));await act(async()=>{});
 expect(api.pageTask).toHaveBeenCalledTimes(1);
 await act(async()=>{vi.advanceTimersByTime(6000);});
 expect(api.pageTask).toHaveBeenCalledTimes(2);
 expect(screen.getByText('Review ready')).toBeVisible();
 expect(api.controlWorkflow).not.toHaveBeenCalled();
});
