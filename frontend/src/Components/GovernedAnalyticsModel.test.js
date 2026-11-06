import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import GovernedAnalyticsModel from './GovernedAnalyticsModel';
import GraphSnapshotSource from './GraphSnapshotSource';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{analyticsModels:vi.fn(),semanticFields:vi.fn(),analyticsMembers:vi.fn(),analyticsValues:vi.fn(),saveAnalyticsModel:vi.fn(),approveAnalyticsModel:vi.fn(),graphSnapshotSources:vi.fn(),definitions:vi.fn(),runDefinition:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'test-token'}));
beforeEach(()=>{vi.clearAllMocks();api.analyticsModels.mockResolvedValue({data:{models:[]}});api.semanticFields.mockResolvedValue({data:{rows:[]}});api.analyticsMembers.mockResolvedValue({data:{members:[]}});});
test('saved model approval is separate from saving and publication',async()=>{
 api.analyticsModels.mockResolvedValue({data:{models:[{model_id:'approved-model',name:'Portfolio',version:'1.0.0',status:'draft',definition:{scope:'Pinned revision A only',kpis:[],expected_bom:[]}}]}});
 api.approveAnalyticsModel.mockResolvedValue({data:{model_id:'approved-model'}});
 render(<GovernedAnalyticsModel datasetId="dataset" businessModel={{product_class:'urn:P',part_class:'urn:A'}} selected="approved-model" onSelect={()=>{}}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Approve this model version'}));
 await waitFor(()=>expect(api.approveAnalyticsModel).toHaveBeenCalledTimes(1));expect(api.saveAnalyticsModel).not.toHaveBeenCalled();expect(api.runDefinition).not.toHaveBeenCalled();
});
test('snapshot submission pins publication and rapid clicks submit once',async()=>{
 api.graphSnapshotSources.mockResolvedValue({data:{sources:[{ontology_id:'source',name:'Business graph',publication_id:'published-7'}]}});
 api.definitions.mockResolvedValue({data:{jobs:[{job_id:'review',version:'1.0.0',name:'Approved native analysis',job_type:'graph-source-snapshot',lifecycle_state:'approved',enabled:true}]}});
 let complete;api.runDefinition.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
 render(<GraphSnapshotSource/>);fireEvent.click(screen.getByText('Use a published graph as reporting data'));
 await screen.findByRole('option',{name:'Business graph · source'});fireEvent.change(screen.getByLabelText('Published graph'),{target:{value:'source'}});
 const button=screen.getByRole('button',{name:'Create registered snapshot with worker'});fireEvent.click(button);fireEvent.click(button);
 expect(api.runDefinition).toHaveBeenCalledTimes(1);expect(api.runDefinition.mock.calls[0][2]).toMatchObject({ontology_id:'source',graph_publication_id:'published-7',algorithm:'graph-snapshot'});
 await act(async()=>complete({data:{run_manifest:{run_id:'retained'}}}));expect(screen.getByRole('link',{name:'Inspect snapshot run'})).toHaveAttribute('href','#/data-flow?run_id=retained');
});
