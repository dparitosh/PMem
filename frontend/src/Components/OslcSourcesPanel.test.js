import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import OslcSourcesPanel from './OslcSourcesPanel';
import {apiClient,dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()},dataPipelineAPI:{definitions:vi.fn(),runDefinition:vi.fn(),createDefinition:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(service,path)=>path}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'test-scope'}));
beforeEach(()=>{vi.clearAllMocks();localStorage.clear();apiClient.get.mockResolvedValue({data:{syncs:[{sync_id:'s',resource_type:'requirements',resource_count:1,complete:true,content_sha256:'digest',provider_url:'https://provider',requested_by:'reader'}]}});dataPipelineAPI.definitions.mockResolvedValue({data:{definitions:[{job_id:'prepare',version:'1.0.0',job_type:'oslc-snapshot-ingest',lifecycle_state:'approved',enabled:true,name:'Prepare requirements'}]}});});
test('selects retained records and approved workflow without typing identifiers',async()=>{
 dataPipelineAPI.runDefinition.mockResolvedValue({data:{run:{run_id:'r'}}});render(<OslcSourcesPanel/>);
 await screen.findByRole('option',{name:/requirements · 1 records/});
 fireEvent.change(screen.getByLabelText('Provider snapshot'),{target:{value:'s'}});
 fireEvent.change(screen.getByLabelText('Approved preparation workflow'),{target:{value:'prepare@1.0.0'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare selected records'}));
 expect(await screen.findByRole('link',{name:'Review processing and retained evidence'})).toHaveAttribute('href','#/data-flow?view=runs&run_id=r');
 expect(dataPipelineAPI.runDefinition).toHaveBeenCalledTimes(1);
});
test('incomplete snapshots cannot be prepared',async()=>{
 apiClient.get.mockResolvedValue({data:{syncs:[{sync_id:'s',resource_type:'requirements',resource_count:1,complete:false}]}});
 render(<OslcSourcesPanel/>);await screen.findByRole('option',{name:/Incomplete/});
 fireEvent.change(screen.getByLabelText('Provider snapshot'),{target:{value:'s'}});
 expect(screen.getByRole('button',{name:'Prepare selected records'})).toBeDisabled();
});
