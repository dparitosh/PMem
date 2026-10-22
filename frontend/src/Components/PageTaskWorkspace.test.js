import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
