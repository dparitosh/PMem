import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import OslcSourcesPanel from './OslcSourcesPanel';
import {apiClient,dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()},dataPipelineAPI:{definitions:vi.fn(),runDefinition:vi.fn(),createDefinition:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(service,path)=>path}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'test-scope'}));
const snapshot={sync_id:'snapshot-one',resource_type:'requirements',resource_count:1,complete:true,status:'staged',content_sha256:'a'.repeat(64),created_at:'2026-11-14T00:00:00Z',provider_url:'https://provider.example',requested_by:'reader'};
const workflow={job_id:'prepare',version:'1.0.0',job_type:'oslc-snapshot-ingest',lifecycle_state:'approved',enabled:true,name:'Prepare requirements'};
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();apiClient.get.mockResolvedValue({data:{syncs:[snapshot]}});api.definitions.mockResolvedValue({data:{definitions:[workflow]}});});
async function choose(){
 await screen.findByRole('option',{name:/^requirements · 1 records/});
 fireEvent.change(screen.getByLabelText('Provider snapshot'),{target:{value:snapshot.sync_id}});
 fireEvent.change(screen.getByLabelText('Approved preparation workflow'),{target:{value:'prepare@1.0.0'}});
}

test('selects retained records and approved workflow without typing identifiers',async()=>{
 api.runDefinition.mockResolvedValue({data:{run:{run_id:'r',status:'queued'}}});render(<OslcSourcesPanel/>);await choose();
 fireEvent.click(screen.getByRole('button',{name:'Prepare selected records'}));
 expect(await screen.findByRole('link',{name:'Review processing and retained evidence'})).toHaveAttribute('href','#/data-flow?view=runs&run_id=r');
 expect(api.runDefinition).toHaveBeenCalledTimes(1);
});

test('missing lifecycle grant shows setup rather than false workflow-creation guidance',async()=>{
 apiClient.get.mockRejectedValue({response:{status:403,data:{detail:'No lifecycle resource grant'}}});
 render(<OslcSourcesPanel/>);
 expect(await screen.findByText('Lifecycle snapshot access needs setup')).toBeVisible();
 expect(screen.getByText(/Your API sign-in is valid/)).toBeVisible();
 expect(screen.getByRole('link',{name:'Review lifecycle service setup'})).toHaveAttribute('href','#/admin?view=services');
 expect(screen.queryByLabelText('Provider snapshot')).not.toBeInTheDocument();
 expect(screen.queryByText('Create preparation workflow draft')).not.toBeInTheDocument();
 expect(screen.queryByText('Prepare selected records')).not.toBeInTheDocument();
 expect(api.createDefinition).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('Request details'));
 expect(screen.getByText('No lifecycle resource grant')).toBeVisible();
});

test('refresh after permission setup distinguishes no retained snapshots',async()=>{
 apiClient.get.mockRejectedValueOnce({response:{status:403,data:{detail:'No lifecycle resource grant'}}});
 render(<OslcSourcesPanel/>);await screen.findByText('Lifecycle snapshot access needs setup');
 apiClient.get.mockResolvedValue({data:{syncs:[]}});
 fireEvent.click(screen.getByText('Refresh provider snapshots'));
 expect(await screen.findByText(/No retained provider snapshots are available/)).toBeVisible();
 expect(screen.queryByText('Lifecycle snapshot access needs setup')).not.toBeInTheDocument();
 expect(screen.queryByText('Create preparation workflow draft')).not.toBeInTheDocument();
});

test('failed refresh removes stale preparation choices',async()=>{
 render(<OslcSourcesPanel/>);await choose();expect(screen.getByText('Prepare selected records')).toBeEnabled();
 apiClient.get.mockRejectedValueOnce(new Error('Temporary service failure'));
 fireEvent.click(screen.getByText('Refresh provider snapshots'));
 await screen.findByRole('alert');
 expect(screen.queryByText('Prepare selected records')).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Provider snapshot')).not.toBeInTheDocument();
 expect(api.runDefinition).not.toHaveBeenCalled();
});

test('removed approved workflow clears selection and prevents preparation',async()=>{
 render(<OslcSourcesPanel/>);await choose();expect(screen.getByText('Prepare selected records')).toBeEnabled();
 api.definitions.mockResolvedValueOnce({data:{definitions:[]}});
 fireEvent.click(screen.getByText('Refresh provider snapshots'));
 await screen.findByText('Create preparation workflow draft');
 expect(screen.getByLabelText('Approved preparation workflow')).toHaveValue('');
 expect(screen.getByText('Prepare selected records')).toBeDisabled();
});

test.each([
 {...snapshot,complete:'false'}, {...snapshot,resource_count:-1}, {...snapshot,provider_url:{}}, null,
])('invalid snapshot metadata produces a controlled unavailable state',async(value)=>{
 apiClient.get.mockResolvedValue({data:{syncs:[value]}});render(<OslcSourcesPanel/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Provider snapshots could not be loaded');
 expect(screen.queryByText('Prepare selected records')).not.toBeInTheDocument();
});

test('incomplete snapshots cannot be prepared',async()=>{
 apiClient.get.mockResolvedValue({data:{syncs:[{...snapshot,complete:false}]}});render(<OslcSourcesPanel/>);
 await screen.findByRole('option',{name:/Incomplete/});
 fireEvent.change(screen.getByLabelText('Provider snapshot'),{target:{value:snapshot.sync_id}});
 expect(screen.getByText('Prepare selected records')).toBeDisabled();
});

test('missing provenance explains why a complete snapshot cannot be prepared',async()=>{
 apiClient.get.mockResolvedValue({data:{syncs:[{...snapshot,content_sha256:null}]}});render(<OslcSourcesPanel/>);await choose();
 expect(screen.getByText(/missing retained source evidence/)).toBeVisible();
 expect(screen.queryByText(/Ready for preparation review/)).not.toBeInTheDocument();
 expect(screen.getByText('Prepare selected records')).toBeDisabled();
});

test.each([{status:'staged_partial'},{resource_count:1001}])('worker-ineligible snapshots remain held',async(change)=>{
 const item={...snapshot,...change};apiClient.get.mockResolvedValue({data:{syncs:[item]}});
 render(<OslcSourcesPanel/>);await screen.findByRole('option',{name:/^requirements/});
 fireEvent.change(screen.getByLabelText('Provider snapshot'),{target:{value:snapshot.sync_id}});
 fireEvent.change(screen.getByLabelText('Approved preparation workflow'),{target:{value:'prepare@1.0.0'}});
 expect(screen.getByText('Prepare selected records')).toBeDisabled();
});

test('missing run acknowledgement reports an unknown outcome and preserves its submission key',async()=>{
 api.runDefinition.mockResolvedValue({data:{}});render(<OslcSourcesPanel/>);await choose();
 fireEvent.click(screen.getByText('Prepare selected records'));
 expect(await screen.findByRole('alert')).toHaveTextContent('Acquisition run was not confirmed');
 expect(screen.getByRole('link',{name:'Inspect retained processing runs'})).toHaveAttribute('href','#/data-flow?view=runs');
 expect(localStorage.getItem('depo:oslc-preparation:'+snapshot.sync_id+':prepare@1.0.0')).toBeTruthy();
 expect(api.runDefinition).toHaveBeenCalledTimes(1);
});

test('standard run_manifest receipt is accepted and duplicate clicks submit only once',async()=>{
 let resolve;api.runDefinition.mockImplementation(()=>new Promise(r=>{resolve=r;}));render(<OslcSourcesPanel/>);await choose();
 const button=screen.getByText('Prepare selected records');fireEvent.click(button);fireEvent.click(button);
 expect(api.runDefinition).toHaveBeenCalledTimes(1);
 const payload=api.runDefinition.mock.calls[0][2];
 await act(async()=>resolve({data:{status:'queued',submission_id:payload.idempotency_key,run_manifest:{run_id:'manifest-run',status:'queued'}}}));
 expect(await screen.findByRole('link',{name:'Review processing and retained evidence'})).toHaveAttribute('href','#/data-flow?view=runs&run_id=manifest-run');
});

test('late acknowledgement after reconnect cannot restore the previous run link',async()=>{
 let resolve;api.runDefinition.mockImplementation(()=>new Promise(r=>{resolve=r;}));render(<OslcSourcesPanel/>);await choose();
 fireEvent.click(screen.getByText('Prepare selected records'));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>resolve({data:{run:{run_id:'old-run',status:'queued'}}}));
 await waitFor(()=>expect(apiClient.get).toHaveBeenCalledTimes(2));
 expect(screen.queryByRole('link',{name:'Review processing and retained evidence'})).not.toBeInTheDocument();
});

test('unavailable workflow catalog does not imply a missing workflow',async()=>{
 api.definitions.mockRejectedValue(new Error('Workflow registry unavailable'));render(<OslcSourcesPanel/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Preparation workflows could not be loaded');
 expect(screen.queryByText('Create preparation workflow draft')).not.toBeInTheDocument();
});
