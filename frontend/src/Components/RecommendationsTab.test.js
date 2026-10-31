import React from 'react';
import {vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import RecommendationsTab from "../features/recommendations/RecommendationsWorkspace.js";
import {agenticClient} from '../services/agenticApi';
import {API_METHODS} from '../services/apiClient';
vi.mock('../services/agenticApi',()=>({agenticClient:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../services/apiClient',()=>({API_METHODS:{recommendations:{health:vi.fn(),resolve:vi.fn(),changeImpact:vi.fn(),similarParts:vi.fn(),manufacturing:vi.fn()}}}));
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
const selectObject=(name,service='change-impact')=>fireEvent(window,new CustomEvent('dt-rec-prefill',{detail:{service,name,node_id:'selected-object'}}));

test('Similar Parts requests eligible objects and displays business type, revision and source',async()=>{
 ready();
 API_METHODS.recommendations.resolve.mockResolvedValue({data:{matches:[{node_id:'part-b',name:'Motor',business_type:'part',revision:'B',source:'parts.xml',scope:{ontology_id:'plant'}}],truncated:true,filtered_out:2,selection_scope:'Declared parts and assemblies within bounded name matches'}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}));
 fireEvent.change(screen.getByLabelText('Reference part'),{target:{value:'Motor'}});
 fireEvent.click(screen.getByRole('button',{name:'Find business objects'}));
 expect(await screen.findByText('Revision B')).toBeVisible();
 expect(screen.getByText('parts.xml')).toBeVisible();
 expect(screen.getByText(/2 other or unverified record types were excluded/)).toBeVisible();
 expect(API_METHODS.recommendations.resolve).toHaveBeenCalledWith('Motor',{},expect.objectContaining({analysis:'similar-parts'}));
});

test.each(['Change Impact','Similar Parts','Process Context'])('agent requires selected business identity in %s',async tab=>{
 ready();render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.click(screen.getByRole('tab',{name:tab}));
 const label=tab==='Change Impact'?'Changed item':tab==='Similar Parts'?'Reference part':'Part or assembly';
 fireEvent.change(screen.getByLabelText(label),{target:{value:'Motor'}});
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
 expect(screen.queryByText('Ready to analyse')).toBeNull();
 expect(agenticClient.post).not.toHaveBeenCalled();
 selectObject('Motor',tab==='Change Impact'?'change-impact':tab==='Similar Parts'?'similar-parts':'manufacturing');
 await waitFor(()=>expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeEnabled());
 fireEvent.change(screen.getByLabelText(label),{target:{value:'Another motor'}});
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
});

test('ambiguous direct search shows business objects and retries using the selected identity',async()=>{
 ready();
 API_METHODS.recommendations.similarParts.mockRejectedValueOnce({response:{status:409,data:{detail:'Graph search is bounded; select its node_id and ontology scope'}}})
  .mockResolvedValueOnce({data:{message:'No similar candidates',similar_parts:[]}});
 API_METHODS.recommendations.resolve.mockResolvedValue({data:{matches:[{node_id:'motor-2',name:'INDUCTION MOTOR',scope:{ontology_id:'plant-b'}}],truncated:true}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');direct();
 fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}));
 fireEvent.change(screen.getByLabelText('Reference part'),{target:{value:'induction motor'}});
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await screen.findByRole('region',{name:'Matching business objects'});
 fireEvent.click(screen.getByRole('button',{name:'Use this object'}));
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await waitFor(()=>expect(API_METHODS.recommendations.similarParts).toHaveBeenLastCalledWith('INDUCTION MOTOR',10,{node_id:'motor-2',ontology_id:'plant-b'},expect.anything()));
});

test('inline selected identity is included in the agent context',async()=>{
 ready();
 API_METHODS.recommendations.resolve.mockResolvedValue({data:{matches:[{node_id:'motor-2',name:'Motor',scope:{ontology_id:'plant-b'}}],truncated:false}});
 agenticClient.post.mockResolvedValue({data:{run_id:'goal-selection',status:'running'}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 fireEvent.click(screen.getByRole('button',{name:'Find business objects'}));
 fireEvent.click(await screen.findByRole('button',{name:'Use this object'}));
 fireEvent.click(screen.getByRole('button',{name:'Analyse with agent'}));
 await waitFor(()=>expect(agenticClient.post).toHaveBeenCalledWith(expect.stringContaining('/agents/graph-analyst/goals'),expect.objectContaining({context:expect.objectContaining({node_id:'motor-2',ontology_id:'plant-b'})}),expect.anything()));
});

test('editing a query discards a slow object lookup response',async()=>{
 ready();let resolve;
 API_METHODS.recommendations.resolve.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Motor'}});
 fireEvent.click(screen.getByRole('button',{name:'Find business objects'}));
 const signal=API_METHODS.recommendations.resolve.mock.calls[0][2].signal;
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 resolve({data:{matches:[{node_id:'old',name:'Motor',scope:{}}],truncated:false}});
 await waitFor(()=>expect(signal.aborted).toBe(true));
 expect(screen.queryByRole('region',{name:'Matching business objects'})).toBeNull();
});

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
 ready();const context={page:'quality',node_id:'selected-object',recommendation_service:'change-impact',recommendation_object:'Motor',recommendation_top_n:10};
 agenticClient.post.mockResolvedValue({data:{run_id:'goal-recommendation',goal:'Inspect Motor',status:'completed',context,
  observations:[{id:'observation-2',tool_id:'recommendation.change_impact',status:'completed',result:{message:'No matching graph term was found.',decision_policy:{status:'not_configured'}}}],
  result:{summary:'No matching object was returned.',evidence_steps:['observation-2'],recommendation_observation_id:'observation-2'}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 expect(screen.getByLabelText('Analysis method')).toHaveValue('agent');
 selectObject('Motor');
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

test('an access rejection blocks analysis until access has been verified',async()=>{
 ready();render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 direct();
 fireEvent(window,new Event('depo:access-rejected'));
 expect(screen.getByRole('button',{name:'Analyse'})).toBeDisabled();
 expect(screen.getByText(/API access was rejected. Use Revalidate access/)).toBeVisible();
 expect(screen.queryByText('Graph data available')).toBeNull();
 fireEvent(window,new Event('depo:access-verified'));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Analyse'})).toBeEnabled());
});

test('agent errors do not leave a contradictory ready-to-analyse message',async()=>{
 ready();agenticClient.post.mockRejectedValue(new Error('Service access was rejected'));
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 selectObject('Bearing');
 fireEvent.click(await screen.findByRole('button',{name:'Analyse with agent'}));
 await screen.findByText('Service access was rejected');
 expect(screen.queryByText('Ready to analyse')).toBeNull();
});

test('invalid similarity limits do not disable other agent analyses',async()=>{
 ready();render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}));
 fireEvent.change(screen.getByLabelText('Reference part'),{target:{value:'Bearing'}});
 selectObject('Bearing','similar-parts');
 fireEvent.change(screen.getByLabelText('Results'),{target:{value:''}});
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
 expect(screen.getByText('Choose a whole number of results from 1 to 50.')).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Process Context'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeEnabled());
 expect(screen.queryByText('Choose a whole number of results from 1 to 50.')).toBeNull();
});

test.each(['', '0','51','1.5'])('invalid direct similarity limit %s cannot submit',async value=>{
 ready();render(<RecommendationsTab/>);await screen.findByText('Graph available');direct();
 fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}));
 fireEvent.change(screen.getByLabelText('Reference part'),{target:{value:'Bearing'}});
 fireEvent.change(screen.getByLabelText('Results'),{target:{value}});
 expect(screen.getByRole('button',{name:'Analyse'})).toBeDisabled();
 expect(API_METHODS.recommendations.similarParts).not.toHaveBeenCalled();
});

test('a malformed agent tool catalog gives a recoverable error without enabling submission',async()=>{
 ready();agenticClient.get.mockResolvedValue({data:{tools:{wrong:'shape'}}});
 render(<RecommendationsTab/>);await screen.findByText(/Agent tool catalog is invalid/);
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
 expect(screen.queryByText('Ready to analyse')).toBeNull();
});

test.each([null,[],{impacted_parts:[null]},{change_entity:{name:{raw:'wrong'}}},{realization_chain:[{path_names:'not an array'}]}])('invalid graph evidence is reported without rendering results (%j)',async data=>{
 ready();API_METHODS.recommendations.changeImpact.mockResolvedValue({data});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');direct();
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 expect(await screen.findByRole('alert')).toHaveTextContent(/Recommendation response/);
 expect(screen.queryByRole('heading',{name:'Change Impact results'})).toBeNull();
});

test('unusable completed agent evidence is explicitly reported',async()=>{
 ready();agenticClient.post.mockResolvedValue({data:{run_id:'goal-missing',status:'completed',result:{summary:'No cited observation'}}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');
 selectObject('Bearing');
 fireEvent.click(screen.getByRole('button',{name:'Analyse with agent'}));
 expect(await screen.findByText(/completed without usable evidence/)).toBeVisible();
 expect(screen.queryByRole('heading',{name:'Change Impact results'})).toBeNull();
});

test('object edits cancel in-flight analysis and late failures cannot replace current state',async()=>{
 ready();let reject;API_METHODS.recommendations.changeImpact.mockImplementation(()=>new Promise((_,failure)=>{reject=failure;}));
 render(<RecommendationsTab/>);await screen.findByText('Graph available');direct();
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Bearing'}});
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 const signal=API_METHODS.recommendations.changeImpact.mock.calls[0][2].signal;
 fireEvent.change(screen.getByLabelText('Changed item'),{target:{value:'Shaft'}});
 expect(signal.aborted).toBe(true);reject(new Error('Old object failed'));
 await waitFor(()=>expect(screen.queryByText('Old object failed')).toBeNull());
 expect(screen.getByRole('button',{name:'Analyse'})).toBeEnabled();
});

test('process context submits the selected scoped identity',async()=>{
 ready();API_METHODS.recommendations.manufacturing.mockResolvedValue({data:{message:'No linked processes'}});
 render(<RecommendationsTab/>);await screen.findByText('Graph available');direct();
 fireEvent(window,new CustomEvent('dt-rec-prefill',{detail:{service:'manufacturing',name:'Bearing',node_id:'selected',scope:{ontology_id:'plant'}}}));
 fireEvent.click(screen.getByRole('button',{name:'Analyse'}));
 await screen.findByRole('heading',{name:'Process Context results'});
 expect(API_METHODS.recommendations.manufacturing).toHaveBeenCalledWith('Bearing',{node_id:'selected',ontology_id:'plant'},expect.objectContaining({timeout:60000}));
});

test('non-string prefill data cannot crash the object input',async()=>{
 ready();render(<RecommendationsTab/>);await screen.findByText('Graph available');
 fireEvent(window,new CustomEvent('dt-rec-prefill',{detail:{service:'change-impact',name:{raw:'not a name'}}}));
 expect(screen.getByLabelText('Changed item')).toHaveValue('');
 expect(screen.getByRole('button',{name:'Analyse with agent'})).toBeDisabled();
});
