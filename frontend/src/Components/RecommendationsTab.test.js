import React from 'react';
import {vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import RecommendationsTab from "../features/recommendations/RecommendationsWorkspace.js";
import {agenticClient} from '../services/agenticApi';
import {API_METHODS} from '../services/apiClient';
vi.mock('../services/agenticApi',()=>({agenticClient:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../services/apiClient',()=>({API_METHODS:{recommendations:{health:vi.fn(),changeImpact:vi.fn(),similarParts:vi.fn(),manufacturing:vi.fn()}}}));
test('readiness can be retried after dependencies recover',async()=>{
 API_METHODS.recommendations.health.mockResolvedValueOnce({data:{status:'degraded',readiness:{scenario_ready:false,message:'Service offline'}}})
 .mockResolvedValueOnce({data:{status:'degraded',readiness:{scenario_ready:false,message:'Service recovering'}}});
 render(<RecommendationsTab/>);
 await screen.findByText('Service offline');
 fireEvent.click(screen.getByText('Retry recommendation readiness'));
 await screen.findByText('Service recovering');
 expect(API_METHODS.recommendations.health).toHaveBeenCalledTimes(2);
 expect(API_METHODS.recommendations.health.mock.calls[0][0].signal).toBeInstanceOf(AbortSignal);
});


test('credential changes abort readiness and fetch a current session result', async () => {
 API_METHODS.recommendations.health.mockReset();
 API_METHODS.recommendations.health.mockImplementationOnce(() => new Promise(() => {}))
 .mockResolvedValue({data:{status:'degraded',readiness:{scenario_ready:false,message:'Current session readiness'}}});
 render(<RecommendationsTab/>);
 const oldSignal = API_METHODS.recommendations.health.mock.calls[0][0].signal;
 fireEvent(window, new Event('depo:credentials-cleared'));
 await screen.findByText('Current session readiness');
 expect(oldSignal.aborted).toBe(true);
 expect(API_METHODS.recommendations.health).toHaveBeenCalledTimes(2);
});

const ready=()=>API_METHODS.recommendations.health.mockResolvedValue({data:{status:'ok',readiness:{scenario_ready:true,message:'Graph available',service_readiness:{'change-impact':true,'similar-parts':true,manufacturing:true}}}});
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();agenticClient.get.mockResolvedValue({data:{read_goal_capabilities:{recommendation_evidence:1},tools:[{id:'recommendation.change_impact'},{id:'recommendation.similar_parts'},{id:'recommendation.manufacturing'}]}});});
const direct=()=>fireEvent.change(screen.getByLabelText('Analysis method'),{target:{value:'graph'}});

test('graph prefill retains identity and scope until the user edits the object',async()=>{
 ready(); API_METHODS.recommendations.changeImpact.mockResolvedValue({data:{message:'No linked evidence'}});
 render(<RecommendationsTab/>); await screen.findByText('Graph available'); direct();
 fireEvent(window,new CustomEvent('dt-rec-prefill',{detail:{service:'change-impact',name:'Motor',node_id:'revision-2',scope:{ontology_id:'plant'}}}));
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await waitFor(()=>expect(API_METHODS.recommendations.changeImpact).toHaveBeenCalledWith('Motor',{node_id:'revision-2',ontology_id:'plant'},expect.anything()));
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await waitFor(()=>expect(API_METHODS.recommendations.changeImpact).toHaveBeenLastCalledWith('Bearing',{},expect.anything()));
});
test('one service selector and input replace duplicate scenarios and misrouted sample prompts',async()=>{
 ready();render(<RecommendationsTab/>);
 await screen.findByText('Graph available');
 expect(screen.getAllByRole('heading',{name:'Recommendations'})).toHaveLength(1);
 expect(screen.getAllByRole('tab')).toHaveLength(3);
 expect(screen.queryByText('Use sample')).toBeNull();
 expect(screen.getByLabelText('Changed item')).toBeVisible();
 fireEvent.keyDown(screen.getByRole('tab',{name:'Change Impact'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'Similar Parts'})).toHaveFocus();
 expect(screen.getByLabelText('Reference part')).toBeVisible();
 expect(API_METHODS.recommendations.changeImpact).not.toHaveBeenCalled();
});
test.each([false,{ready:false,message:'Missing process links'}])('service-specific readiness blocks analysis (%j)',async serviceReadiness=>{
 API_METHODS.recommendations.health.mockResolvedValue({data:{status:'ok',readiness:{scenario_ready:true,message:'Graph available',service_readiness:{manufacturing:serviceReadiness}}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.click(screen.getByRole('tab',{name:'Process Context'}));
 fireEvent.change(screen.getByLabelText('Part or assembly'),{target:{value:'Motor'}});
 direct();
 expect(screen.getByRole('button',{name:'Analyse'})).toBeDisabled();
 expect(API_METHODS.recommendations.manufacturing).not.toHaveBeenCalled();
});
test('routes similar-part requests correctly and clears results when the limit changes',async()=>{
 ready();API_METHODS.recommendations.similarParts.mockResolvedValue({data:{source_part:{name:'Motor'},similar_parts:[],ranking_scope:'Bounded lexical candidates',decision_policy:{status:'not_configured'}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}));
 fireEvent.change(screen.getByLabelText('Reference part'),{target:{value:'Motor'}});
 direct();
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 expect(await screen.findByRole('heading',{name:'Similar Parts results'})).toBeVisible();
 expect(API_METHODS.recommendations.similarParts).toHaveBeenCalledWith('Motor',10,{},expect.objectContaining({signal:expect.any(AbortSignal),timeout:60000}));
 expect(API_METHODS.recommendations.changeImpact).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Results'),{target:{value:'5'}});
 expect(screen.queryByRole('heading',{name:'Similar Parts results'})).toBeNull();
});
test('switching service cancels a pending result and ignores its late response',async()=>{
 ready();let finish;API_METHODS.recommendations.changeImpact.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 direct();
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 const signal=API_METHODS.recommendations.changeImpact.mock.calls[0][2].signal;
 fireEvent.click(screen.getByRole('tab',{name:'Process Context'}));
 expect(signal.aborted).toBe(true);
 finish({data:{message:'Stale analysis'}});
 await waitFor(()=>expect(screen.queryByText('Stale analysis')).toBeNull());
});
test('empty graph results do not claim a successful structured recommendation',async()=>{
 ready();API_METHODS.recommendations.changeImpact.mockResolvedValue({data:{message:'No matching graph term was found.',decision_policy:{status:'not_configured'}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Missing object'}});
 direct();
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 expect(await screen.findByText('No structured recommendation evidence')).toBeVisible();
 expect(screen.queryByText('Analysis completed')).toBeNull();
});

test('agent mode submits the selected analysis through the existing read-goal endpoint and renders cited policy evidence',async()=>{
 ready();const context={page:'quality',recommendation_service:'change-impact',recommendation_object:'Motor',recommendation_top_n:10};
 agenticClient.post.mockResolvedValue({data:{run_id:'goal-recommendation',goal:'Inspect Motor',status:'completed',context,
  observations:[{id:'observation-2',tool_id:'recommendation.change_impact',status:'completed',result:{message:'No matching graph term was found.',decision_policy:{status:'not_configured'}}}],
  result:{summary:'No matching object was returned.',evidence_steps:['observation-2'],recommendation_observation_id:'observation-2'}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 expect(screen.getByLabelText('Analysis method')).toHaveValue('agent');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 fireEvent.click(await screen.findByRole('button',{name:'Analyse with agent'}));
 expect(await screen.findByRole('heading',{name:'Change Impact results'})).toBeVisible();
 expect(agenticClient.post).toHaveBeenCalledWith(expect.stringContaining('/agents/graph-analyst/goals'),expect.objectContaining({context,submission_id:expect.any(String)}),expect.anything());
 expect(API_METHODS.recommendations.changeImpact).not.toHaveBeenCalled();
 expect(screen.getByText(/No shared decision policy is configured for this operation/)).toBeVisible();
 expect(screen.queryByRole('heading',{name:'Investigate a goal with the agent'})).toBeNull();
});

test('legacy backend cannot present agent completion without the new evidence contract',async()=>{
 ready();agenticClient.get.mockResolvedValue({data:{tools:[{id:'recommendation.change_impact'}]}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 expect(await screen.findByText(/Agent investigation is awaiting the updated PMem backend/)).toBeVisible();
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
 expect(agenticClient.post).not.toHaveBeenCalled();
});

test('session expiry clears direct graph evidence and rechecks service readiness',async()=>{
 ready();API_METHODS.recommendations.changeImpact.mockResolvedValue({data:{message:'Previous session evidence'}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 direct();fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await screen.findAllByText('Previous session evidence');
 const previous=API_METHODS.recommendations.health.mock.calls.length;
 fireEvent(window,new Event('depo:session-expired'));
 await waitFor(()=>expect(screen.queryAllByText('Previous session evidence')).toHaveLength(0));
 await waitFor(()=>expect(API_METHODS.recommendations.health).toHaveBeenCalledTimes(previous+1));
});
