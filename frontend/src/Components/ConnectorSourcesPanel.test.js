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
 api.registerConnector.mockImplementation(payload=>Promise.resolve({data:{...source,source_id:payload.source_id}}));render(<ConnectorSourcesPanel/>);
 await screen.findByRole('option',{name:'Local parts · Parquet'});
 fireEvent.change(screen.getByRole('combobox',{name:'Connection'}),{target:{value:'parts-profile'}});
 fireEvent.change(screen.getByRole('combobox',{name:'Resource'}),{target:{value:'parts'}});
 fireEvent.change(screen.getByRole('textbox',{name:'Source display name'}),{target:{value:'Local inventory'}});
 fireEvent.click(screen.getByRole('button',{name:'Register source reference'}));
 await waitFor(()=>expect(api.registerConnector).toHaveBeenCalledTimes(1));
 expect(api.registerConnector).toHaveBeenCalledWith(expect.objectContaining({profile_id:'parts-profile',resource:'parts',name:'Local inventory'}),'test-token');
 expect(screen.queryByRole('textbox',{name:/password|connection string/i})).not.toBeInTheDocument();
 await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh connections and jobs'})).toBeEnabled());
 expect(screen.getByText('Source reference registered. Select an approved acquisition job below.')).toBeVisible();
 await waitFor(()=>expect(api.connectorSources).toHaveBeenCalledTimes(2));
 await waitFor(()=>expect(screen.getByRole('combobox',{name:'Registered source'})).toHaveValue(api.registerConnector.mock.calls[0][0].source_id));
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
 api.runDefinition.mockRejectedValue(new Error('Connection lost'));api.connectorSubmission.mockResolvedValue({data:{status:'completed',run_manifest:{run_id:'retained-run',status:'completed'}}});
 render(<ConnectorSourcesPanel/>);await choose();fireEvent.click(screen.getByRole('button',{name:'Acquire records with worker'}));
 await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Check retained acquisition'}));
 expect(await screen.findByRole('link',{name:'Open acquisition run'})).toHaveAttribute('href','#/data-flow?run_id=retained-run');expect(api.runDefinition).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Prepare another acquisition'}));expect(localStorage.getItem('depo:connector-acquisition:v1')).toBeNull();
});

test('failed inventory is unavailable rather than empty and can be refreshed',async()=>{
 api.connectorProfiles.mockRejectedValueOnce(new Error('Service unavailable'));
 render(<ConnectorSourcesPanel/>);await screen.findByRole('alert');
 expect(screen.getByText(/Connection availability is unknown/)).toBeVisible();
 expect(screen.queryByText(/No enterprise connection profiles are configured/)).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Create acquisition job draft'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Acquire records with worker'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Refresh connections and jobs'}));
 await screen.findByRole('option',{name:'Local parts · Parquet'});
 expect(screen.queryByText(/Connection availability is unknown/)).not.toBeInTheDocument();
});

test('failed refresh removes stale source selections and prevents acquisition',async()=>{
 render(<ConnectorSourcesPanel/>);await choose();
 api.definitions.mockRejectedValueOnce(new Error('Access rejected'));
 fireEvent.click(screen.getByRole('button',{name:'Refresh connections and jobs'}));
 await screen.findByRole('alert');
 expect(screen.queryByRole('option',{name:'LOCAL TEST parts · Parquet'})).not.toBeInTheDocument();
 expect(screen.getByRole('combobox',{name:'Registered source'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Acquire records with worker'})).toBeDisabled();
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test('retained receipt can be checked when unrelated inventory loading failed',async()=>{
 localStorage.setItem('depo:connector-acquisition:v1',JSON.stringify({key:'saved-intent',source:'parts-source',job:'source-acquisition@1.0.0'}));
 api.connectorProfiles.mockRejectedValue(new Error('Inventory offline'));
 api.connectorSubmission.mockResolvedValue({data:{status:'completed',run_manifest:{run_id:'retained-run',status:'completed'}}});
 render(<ConnectorSourcesPanel/>);await screen.findByRole('alert');
 fireEvent.click(screen.getByRole('button',{name:'Check retained acquisition'}));
 expect(await screen.findByRole('link',{name:'Open acquisition run'})).toHaveAttribute('href','#/data-flow?run_id=retained-run');
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test.each([null,{...profile,resources:null},{...profile,configured:'true'}])('malformed profiles fail closed without crashing the page',async(bad)=>{
 api.connectorProfiles.mockResolvedValue({data:{profiles:[bad]}});
 render(<ConnectorSourcesPanel/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Invalid connector workspace response');
 expect(screen.getByRole('button',{name:'Register source reference'})).toBeDisabled();
});

test.each([-1,0,'50'])('invalid continuation offsets cannot drive paging requests',async(next)=>{
 api.connectorSources.mockResolvedValue({data:{sources:[source],next_offset:next}});
 render(<ConnectorSourcesPanel/>);await screen.findByRole('alert');
 expect(screen.getByRole('button',{name:'Next sources'})).toBeDisabled();
});

test('removed resource is cleared after profile refresh and cannot be registered',async()=>{
 render(<ConnectorSourcesPanel/>);await screen.findByRole('option',{name:'Local parts · Parquet'});
 fireEvent.change(screen.getByRole('combobox',{name:'Connection'}),{target:{value:profile.profile_id}});
 fireEvent.change(screen.getByRole('combobox',{name:'Resource'}),{target:{value:'parts'}});
 fireEvent.change(screen.getByRole('textbox',{name:'Source display name'}),{target:{value:'Inventory'}});
 expect(screen.getByRole('button',{name:'Register source reference'})).toBeEnabled();
 api.connectorProfiles.mockResolvedValue({data:{profiles:[{...profile,resources:['revised-parts']}]}});
 fireEvent.click(screen.getByRole('button',{name:'Refresh connections and jobs'}));
 await screen.findByRole('option',{name:'revised-parts'});
 expect(screen.getByRole('combobox',{name:'Resource'})).toHaveValue('');
 expect(screen.getByRole('button',{name:'Register source reference'})).toBeDisabled();
 expect(api.registerConnector).not.toHaveBeenCalled();
});

test('malformed receipt preserves the last confirmed run and does not replay',async()=>{
 const retained={key:'saved-intent',source:'parts-source',job:'source-acquisition@1.0.0',run_id:'confirmed-run',status:'running'};
 localStorage.setItem('depo:connector-acquisition:v1',JSON.stringify(retained));
 api.connectorSubmission.mockResolvedValue({data:{status:'completed',run_manifest:{run_id:'wrong-run',status:'completed'}}});
 render(<ConnectorSourcesPanel/>);await screen.findByRole('option',{name:'Local parts · Parquet'});
 fireEvent.click(screen.getByRole('button',{name:'Check retained acquisition'}));
 await screen.findByRole('alert');
 expect(JSON.parse(localStorage.getItem('depo:connector-acquisition:v1'))).toEqual(retained);
 expect(screen.getByRole('link',{name:'Open acquisition run'})).toHaveAttribute('href','#/data-flow?run_id=confirmed-run');
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test('late acquisition response cannot replace a different tab submission',async()=>{
 let finish;api.runDefinition.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<ConnectorSourcesPanel/>);await choose();
 fireEvent.click(screen.getByRole('button',{name:'Acquire records with worker'}));
 const newer={key:'another-tab',source:'other-source',job:'source-acquisition@1.0.0'};
 localStorage.setItem('depo:connector-acquisition:v1',JSON.stringify(newer));
 finish({data:{run_manifest:{run_id:'old-run',status:'queued'}}});
 await screen.findByRole('alert');
 expect(JSON.parse(localStorage.getItem('depo:connector-acquisition:v1'))).toEqual(newer);
 expect(screen.queryByRole('link',{name:'Open acquisition run'})).not.toBeInTheDocument();
});
