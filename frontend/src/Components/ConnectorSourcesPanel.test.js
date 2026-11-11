import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import ConnectorSourcesPanel from './ConnectorSourcesPanel';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{connectorProfiles:vi.fn(),connectorSources:vi.fn(),definitions:vi.fn(),registerConnector:vi.fn(),runDefinition:vi.fn(),connectorSubmission:vi.fn(),createDefinition:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'test-token'}));
const profile={profile_id:'parts-profile',name:'Local parts',kind:'Parquet',resources:['parts'],configured:true};
const source={source_id:'parts-source',name:'LOCAL TEST parts',kind:'Parquet'};
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();api.connectorProfiles.mockResolvedValue({data:{profiles:[profile]}});api.connectorSources.mockResolvedValue({data:{sources:[source],next_offset:null}});api.definitions.mockResolvedValue({data:{definitions:[{job_id:'source-acquisition',name:'Source acquisition',version:'1.0.0',job_type:'registered-source-ingest',lifecycle_state:'approved',enabled:true}]}});});
async function choose(){await screen.findByRole('option',{name:'LOCAL TEST parts · Parquet'});fireEvent.change(screen.getByRole('combobox',{name:'Registered source'}),{target:{value:'parts-source'}});fireEvent.change(screen.getByRole('combobox',{name:'Approved acquisition job'}),{target:{value:'source-acquisition@1.0.0'}});}

test('source and resource are selected; credentials and locations are not entered in the browser',async()=>{
 api.registerConnector.mockResolvedValue({data:source});render(<ConnectorSourcesPanel/>);
 await screen.findByRole('option',{name:'Local parts · Parquet'});
 fireEvent.change(screen.getByRole('combobox',{name:'Connection'}),{target:{value:'parts-profile'}});
 fireEvent.change(screen.getByRole('combobox',{name:'Resource'}),{target:{value:'parts'}});
 fireEvent.change(screen.getByRole('textbox',{name:'Source display name'}),{target:{value:'Local inventory'}});
 fireEvent.click(screen.getByRole('button',{name:'Register source reference'}));
 await waitFor(()=>expect(api.registerConnector).toHaveBeenCalledTimes(1));
 expect(api.registerConnector).toHaveBeenCalledWith(expect.objectContaining({profile_id:'parts-profile',resource:'parts',name:'Local inventory'}),'test-token');
 expect(screen.queryByRole('textbox',{name:/password|connection string/i})).not.toBeInTheDocument();
});

test('acquisition retains one idempotent request and late reconnect responses cannot restore old run links',async()=>{
 let resolve;api.runDefinition.mockImplementation(()=>new Promise(r=>{resolve=r;}));render(<ConnectorSourcesPanel/>);await choose();
 const button=screen.getByRole('button',{name:'Acquire records with worker'});fireEvent.click(button);fireEvent.click(button);
 expect(api.runDefinition).toHaveBeenCalledTimes(1);
 const payload=api.runDefinition.mock.calls[0][2];expect(payload).toMatchObject({source_id:'parts-source',idempotency_key:expect.any(String)});
 fireEvent(window,new Event('depo:session-replaced'));resolve({data:{run_manifest:{run_id:'old-run',status:'queued'}}});
 await waitFor(()=>expect(api.connectorProfiles.mock.calls.length).toBeGreaterThan(1));
 expect(screen.queryByRole('link',{name:'Open acquisition run'})).not.toBeInTheDocument();
 expect(JSON.parse(localStorage.getItem('depo:connector-acquisition:v1')).key).toBe(payload.idempotency_key);
});

test('lost acknowledgement keeps the submission for read-only recovery',async()=>{
 api.runDefinition.mockRejectedValue(new Error('Connection lost'));api.connectorSubmission.mockResolvedValue({data:{status:'completed',run_manifest:{run_id:'retained-run'}}});
 render(<ConnectorSourcesPanel/>);await choose();fireEvent.click(screen.getByRole('button',{name:'Acquire records with worker'}));
 await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Check retained acquisition'}));
 expect(await screen.findByRole('link',{name:'Open acquisition run'})).toHaveAttribute('href','#/data-flow?run_id=retained-run');expect(api.runDefinition).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Prepare another acquisition'}));expect(localStorage.getItem('depo:connector-acquisition:v1')).toBeNull();
});
