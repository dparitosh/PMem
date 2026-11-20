import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import {vi,beforeEach,test,expect} from 'vitest';
import GraphAnalyticsPage from './GraphAnalyticsPage';
import {graphApi} from '../services/graphApi';
import {dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{runs:vi.fn()}}));
vi.mock('../services/graphApi',()=>({graphApi:{computationOptions:vi.fn(),computeGraph:vi.fn(),computationEvidence:vi.fn()}}));
const sources=[{ontology_id:'parts',publication_id:'receipt',name:'Drive assembly'}];
const options={sources,nodes:[{node_id:'bearing',name:'Bearing',revision:'A'}],predicates:['urn:hasPart']};
const evidence={ontology_id:'parts',publication_id:'receipt',algorithm:'pagerank',advisory_only:true,approval_granted:false,evidence_id:'retained',result_count:1,results:[{node_id:'bearing',name:'Bearing',score:.4}],coverage:{nodes:2,edges:1},interpretation:'Structural relevance',currentness:'retained snapshot'};
beforeEach(()=>{vi.resetAllMocks();dataPipelineAPI.runs.mockResolvedValue({data:{runs:[]}});window.history.replaceState(null,'','#/graph-analytics');graphApi.computationOptions.mockImplementation(scope=>Promise.resolve({data:scope?options:{sources}}));graphApi.computeGraph.mockResolvedValue({data:evidence});graphApi.computationEvidence.mockResolvedValue({data:evidence});});
async function choose(){fireEvent.change(await screen.findByLabelText('Published source'),{target:{value:'parts'}});await screen.findByText('hasPart');}
test('computes an exact published scope and reads its retained evidence',async()=>{
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.click(screen.getByRole('button',{name:'Analyse graph'}));await screen.findByRole('region',{name:'Graph analysis result'});
 expect(graphApi.computeGraph).toHaveBeenCalledWith({ontology_id:'parts',publication_id:'receipt',algorithm:'pagerank',predicates:['urn:hasPart'],node_id:'',top_n:10},expect.any(AbortSignal));
 expect(screen.getByText(/Approval not granted/)).toBeVisible();
 fireEvent.click(screen.getByText('Source version and retained evidence'));fireEvent.click(screen.getByRole('button',{name:'Read retained evidence'}));
 await waitFor(()=>expect(graphApi.computationEvidence).toHaveBeenCalledWith('retained','parts',expect.any(AbortSignal)));
});
test('seed-dependent analysis requires a named business record',async()=>{
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.change(screen.getByLabelText('Business question'),{target:{value:'node-similarity'}});
 expect(screen.getByRole('button',{name:'Analyse graph'})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Reference record'),{target:{value:'bearing'}});
 expect(screen.getByRole('button',{name:'Analyse graph'})).not.toBeDisabled();
 expect(window.location.hash).toContain('view=node-similarity');
});
test('changing the analysis aborts the old request and rejects its late result',async()=>{
 let finish;graphApi.computeGraph.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.click(screen.getByRole('button',{name:'Analyse graph'}));const signal=graphApi.computeGraph.mock.calls[0][1];
 fireEvent.change(screen.getByLabelText('Business question'),{target:{value:'triangle-count'}});
 expect(signal.aborted).toBe(true);await act(async()=>finish({data:evidence}));
 expect(screen.queryByRole('region',{name:'Graph analysis result'})).toBeNull();
});
test('source read failure is unavailable rather than an empty success',async()=>{
 graphApi.computationOptions.mockRejectedValue(new Error('Source unavailable'));render(<GraphAnalyticsPage/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Source unavailable');
 expect(screen.queryByText('No current published sources are available.')).toBeNull();
});
test('mismatched computation authority is rejected',async()=>{
 graphApi.computeGraph.mockResolvedValue({data:{...evidence,approval_granted:true}});
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();fireEvent.click(screen.getByRole('button',{name:'Analyse graph'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('mismatched evidence');
 expect(screen.queryByRole('region',{name:'Graph analysis result'})).toBeNull();
});

test('traceability names use recorded roles instead of encoded resource identifiers',async()=>{
 window.history.replaceState(null,'','#/graph-analytics?view=traceability');
 graphApi.computeGraph.mockResolvedValue({data:{...evidence,algorithm:'traceability',results:[{nodes:[{node_id:'bearing',name:'Bearing',role:'part'},{node_id:'geometry',name:'scoped%3Aprivate-reference',role:'geometry'}],edges:[{source:'bearing',target:'geometry',predicate:'urn:traceTo'}]}]}});
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.change(screen.getByLabelText('Reference record'),{target:{value:'bearing'}});fireEvent.click(screen.getByRole('button',{name:'Analyse graph'}));
 expect(await screen.findByRole('region',{name:'Graph analysis result'})).toHaveTextContent('geometry (name not recorded)');
 expect(screen.queryByText(/scoped%3Aprivate-reference/)).toBeNull();
});

test('published source choices use the retained file name from their exact run',async()=>{
 dataPipelineAPI.runs.mockResolvedValue({data:{runs:[{run_id:'receipt',source_name:'Motor requirements.xml'}]}});
 render(<GraphAnalyticsPage/>);
 expect(await screen.findByRole('option',{name:'Motor requirements.xml'})).toHaveValue('parts');
});


test('trace paths display the recorded reverse edge direction without exposing XMI IDs as names',async()=>{
 window.history.replaceState(null,'','#/graph-analytics?view=traceability');
 graphApi.computeGraph.mockResolvedValue({data:{...evidence,algorithm:'traceability',results:[{nodes:[{node_id:'bearing',name:'Bearing',role:'part'},{node_id:'process',name:'_19_0_2_4520142_1657856000000000000',role:'process'}],edges:[{source:'process',target:'bearing',predicate:'urn:traceTo'}]}]}});
 render(<GraphAnalyticsPage/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.change(screen.getByLabelText('Reference record'),{target:{value:'bearing'}});fireEvent.click(screen.getByRole('button',{name:'Analyse graph'}));
 const result=await screen.findByRole('region',{name:'Graph analysis result'});
 expect(result).toHaveTextContent('Bearing ← process (name not recorded)');
 expect(result).toHaveTextContent('process (name not recorded) → Bearing: hasPart'.replace('hasPart','traceTo'));
 expect(result).not.toHaveTextContent('_19_0_2_4520142_1657856000000000000');
});


test('embedded algorithm and source changes retain the Memory insights workspace view',async()=>{
 window.history.replaceState(null,'','#/reports?view=graph-analytics');
 render(<GraphAnalyticsPage embedded/>);await waitFor(()=>expect(screen.getByLabelText('Published source')).not.toBeDisabled());await choose();
 fireEvent.change(screen.getByLabelText('Business question'),{target:{value:'triangle-count'}});
 expect(window.location.hash).toContain('#/reports?');
 expect(new URLSearchParams(window.location.hash.split('?')[1]).get('view')).toBe('graph-analytics');
 expect(new URLSearchParams(window.location.hash.split('?')[1]).get('algorithm')).toBe('triangle-count');
 expect(new URLSearchParams(window.location.hash.split('?')[1]).get('ontology_id')).toBe('parts');
});
