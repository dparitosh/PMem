import React from 'react';
import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import {vi,beforeEach,it,expect} from 'vitest';
import NativeChangeActions from './NativeChangeActions';
import {apiClient} from '../services/apiClient';
const credentials=vi.hoisted(()=>({token:'approval-fixture'}));
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=>credentials.token}));
const status=(state=null)=>({preview_id:'p',current_plan_digest:'a'.repeat(64),change_request:state?{state,revision:state==='submitted'?1:state==='accepted'?2:3,history:[]}:null,scope_changed:false,scope:'Create merged draft only',already_applied:false});
beforeEach(()=>{vi.resetAllMocks();credentials.token='approval-fixture';apiClient.get.mockResolvedValue({data:status()});});
const review=()=>fireEvent.click(screen.getByRole('checkbox'));
it('submits exact scope once and does not accept a caller-supplied actor',async()=>{
 let finish;apiClient.post.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<NativeChangeActions previewId="p"/>);await screen.findByText('Not submitted');
 fireEvent.change(screen.getByLabelText('Change review reason'),{target:{value:'Align assembly vocabulary'}});review();
 const button=screen.getByRole('button',{name:'Submit change request'});fireEvent.click(button);fireEvent.click(button);
 expect(apiClient.post).toHaveBeenCalledTimes(1);
 expect(apiClient.post.mock.calls[0][1]).toEqual({action:'submit',expected_revision:0,expected_plan_digest:'a'.repeat(64),reason:'Align assembly vocabulary'});
 await act(async()=>finish({data:status('submitted')}));
 expect(await screen.findByText('Awaiting request review')).toBeVisible();
 expect(screen.getByRole('button',{name:'Accept request (does not execute)'})).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Create authorized merged draft'})).toBeNull();
});
it('accepted request cannot execute until a separate authorization',async()=>{
 apiClient.get.mockResolvedValue({data:status('accepted')});apiClient.post.mockResolvedValue({data:status('authorized')});
 render(<NativeChangeActions previewId="p"/>);await screen.findByText('Request accepted; execution not authorized');review();
 fireEvent.click(screen.getByRole('button',{name:'Authorize merged draft'}));
 expect(await screen.findByText('Merged draft authorized')).toBeVisible();
 expect(screen.getByRole('button',{name:'Create authorized merged draft'})).toBeDisabled();
 expect(apiClient.post.mock.calls[0][1].action).toBe('authorize');
});
it('uncertain execution removes commands until retained status is refreshed',async()=>{
 apiClient.get.mockResolvedValue({data:status('authorized')});apiClient.post.mockRejectedValue({response:{status:504,data:{detail:'Outcome unverified; inspect retained status'}}});
 render(<NativeChangeActions previewId="p"/>);await screen.findByText('Merged draft authorized');review();
 fireEvent.click(screen.getByRole('button',{name:'Create authorized merged draft'}));
 await screen.findByRole('alert');expect(apiClient.post).toHaveBeenCalledTimes(1);
 expect(screen.queryByRole('button',{name:'Create authorized merged draft'})).toBeNull();
});
it('receipt verification is the only recovery action and never asks to replay',async()=>{
 apiClient.get.mockResolvedValue({data:status('needs_recovery')});render(<NativeChangeActions previewId="p"/>);
 await screen.findByText('Outcome needs verification');
 expect(screen.getByRole('button',{name:'Verify retained result'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Create authorized merged draft'})).toBeNull();
});
it('reconnect clears review consent and ignores a late write receipt',async()=>{
 let finish;apiClient.post.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const onChanged=vi.fn();
 render(<NativeChangeActions previewId="p" onChanged={onChanged}/>);await screen.findByText('Not submitted');
 fireEvent.change(screen.getByLabelText('Change review reason'),{target:{value:'Business review'}});review();fireEvent.click(screen.getByRole('button',{name:'Submit change request'}));
 const signal=apiClient.post.mock.calls[0][2].signal;
 fireEvent(window,new Event('depo:session-replaced'));await screen.findByText('Not submitted');
 expect(signal.aborted).toBe(true);expect(screen.getByRole('checkbox')).not.toBeChecked();
 await act(async()=>finish({data:status('submitted')}));expect(screen.getByText('Not submitted')).toBeVisible();expect(onChanged).not.toHaveBeenCalled();
});
it('missing approval credentials cannot submit a request',async()=>{
 credentials.token='';render(<NativeChangeActions previewId="p"/>);await screen.findByText('Not submitted');
 fireEvent.change(screen.getByLabelText('Change review reason'),{target:{value:'Business review'}});review();fireEvent.click(screen.getByRole('button',{name:'Submit change request'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Connect the owning workflow approval access');expect(apiClient.post).not.toHaveBeenCalled();
});
it('historical applied drafts cannot be retroactively approved',async()=>{
 apiClient.get.mockResolvedValue({data:{...status(),already_applied:true}});render(<NativeChangeActions previewId="p"/>);
 expect(await screen.findByText('This historical merge cannot be retroactively approved.')).toBeVisible();
 expect(screen.queryByRole('button',{name:'Submit change request'})).toBeNull();
});

it('rejects malformed retained history without exposing commands',async()=>{
 const data=status('authorized');data.change_request.history={length:1};apiClient.get.mockResolvedValue({data});
 render(<NativeChangeActions previewId="p"/>);await screen.findByRole('alert');
 expect(screen.queryByRole('button',{name:'Create authorized merged draft'})).toBeNull();
});


const mappingStatus=(phase=null)=>({...status(phase),preview_id:'bridge-preview-p',authorization_valid:['authorized','executing','executed','needs_recovery'].includes(phase),publication_id:'bridge-publication-p',scope:'Publish only the reviewed candidate links',
 change_request:phase?{...status(phase).change_request,candidate_ids:['one']}:null,
 candidates:[{candidate_id:'one',source_term:'Rotor',ontology_term:'Part',eligible:true},{candidate_id:'held',source_term:'Unknown record',ontology_term:'Part',eligible:false}]});
const mappingConsent=()=>fireEvent.click(screen.getByRole('checkbox',{name:'I reviewed these exact mapping candidates and their source baseline.'}));
it('requires explicit eligible selection and submits no caller actor for mappings',async()=>{
 apiClient.get.mockResolvedValue({data:mappingStatus()});apiClient.post.mockResolvedValue({data:mappingStatus('submitted')});
 render(<NativeChangeActions kind="bridges" previewId="bridge-preview-p"/>);await screen.findByText('Not submitted');
 expect(screen.getByRole('checkbox',{name:'Include Unknown record to Part'})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Change review reason'),{target:{value:'Review rotor classification'}});mappingConsent();
 expect(screen.getByRole('button',{name:'Submit change request'})).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox',{name:'Include Rotor to Part'}));
 expect(screen.getByRole('checkbox',{name:'I reviewed these exact mapping candidates and their source baseline.'})).not.toBeChecked();
 mappingConsent();fireEvent.click(screen.getByRole('button',{name:'Submit change request'}));
 await screen.findByText('Awaiting request review');
 expect(apiClient.post.mock.calls[0][1]).toEqual({action:'submit',expected_revision:0,expected_plan_digest:'a'.repeat(64),reason:'Review rotor classification',candidate_ids:['one']});
 expect(apiClient.post.mock.calls[0][0]).toContain('/change-control/bridges/bridge-preview-p/request');
 expect(screen.getByRole('checkbox',{name:'Include Rotor to Part'})).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Publish authorized mappings'})).toBeNull();
});
it('mapping acceptance does not expose execution before a separate authorization',async()=>{
 apiClient.get.mockResolvedValue({data:mappingStatus('accepted')});render(<NativeChangeActions kind="bridges" previewId="bridge-preview-p"/>);
 await screen.findByText('Request accepted; execution not authorized');
 expect(screen.getByRole('button',{name:'Authorize selected mappings'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Publish authorized mappings'})).toBeNull();
});
it('mapping reconnect clears unsubmitted candidate selection and consent',async()=>{
 apiClient.get.mockResolvedValue({data:mappingStatus()});render(<NativeChangeActions kind="bridges" previewId="bridge-preview-p"/>);await screen.findByText('Not submitted');
 fireEvent.click(screen.getByRole('checkbox',{name:'Include Rotor to Part'}));mappingConsent();
 fireEvent(window,new Event('depo:session-replaced'));await waitFor(()=>expect(screen.getByRole('checkbox',{name:'Include Rotor to Part'})).not.toBeChecked());
 expect(screen.getByRole('checkbox',{name:'I reviewed these exact mapping candidates and their source baseline.'})).not.toBeChecked();
 expect(apiClient.post).not.toHaveBeenCalled();
});
it('foreign mapping publication identity cannot expose commands',async()=>{
 apiClient.get.mockResolvedValue({data:{...mappingStatus(),publication_id:'foreign'}});render(<NativeChangeActions kind="bridges" previewId="bridge-preview-p"/>);
 await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'Submit change request'})).toBeNull();
});


it('invalid retained mapping authorization cannot show an executable order',async()=>{
 apiClient.get.mockResolvedValue({data:{...mappingStatus('authorized'),authorization_valid:false}});
 render(<NativeChangeActions kind="bridges" previewId="bridge-preview-p"/>);await screen.findByText('Authorization evidence incomplete');
 expect(screen.queryByRole('button',{name:'Publish authorized mappings'})).toBeNull();
 expect(apiClient.post).not.toHaveBeenCalled();
});

it('product acceptance authorizes a version without publishing, delivery offers receipt actions',async()=>{
 const product={...status('accepted'),product_version:'p',authorization_valid:false,product_name:'Engineering evidence',artifact_count:1,contract:{product_id:'p',version:'1'},artifact_evidence:[]};
 apiClient.get.mockResolvedValue({data:product});
 const view=render(<NativeChangeActions previewId="p" kind="product_changes"/>);
 await screen.findByRole('button',{name:'Authorize this product version'});
 expect(screen.queryByRole('button',{name:'Publish authorized product'})).toBeNull();
 view.unmount();apiClient.get.mockResolvedValue({data:{...product,authorization_valid:true,change_request:{...product.change_request,state:'awaiting_delivery'}}});
 render(<NativeChangeActions previewId="p" kind="product_changes"/>);
 await screen.findByRole('button',{name:'Verify package and delivery'});
 expect(screen.getByRole('button',{name:'Retry catalog delivery'})).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Publish authorized product'})).toBeNull();
});

it('pipeline request binds the run and only exposes publication after authorization',async()=>{
 const pipeline={...status('accepted'),run_id:'p',authorization_valid:false,intent:{ontology_id:'parts',source_system:'plm',semantic_release:{asset_id:'model',version:'1'}},partition_sha256:'a'.repeat(64)};
 apiClient.get.mockResolvedValue({data:pipeline});
 render(<NativeChangeActions previewId="p" kind="pipeline"/>);
 await screen.findByRole('button',{name:'Authorize this partition'});
 expect(screen.queryByRole('button',{name:'Publish authorized partition'})).toBeNull();
 apiClient.post.mockResolvedValue({data:{...pipeline,authorization_valid:true,change_request:{...pipeline.change_request,state:'authorized'}}});
 review();fireEvent.click(screen.getByRole('button',{name:'Authorize this partition'}));
 await screen.findByRole('button',{name:'Publish authorized partition'});
 expect(apiClient.post.mock.calls[0][0]).toContain('/pipeline/p/request');
 expect(screen.getByRole('button',{name:'Publish authorized partition'})).toBeDisabled();
 fireEvent.click(screen.getByText('Technical publication destination'));expect(screen.getByText('parts')).toBeVisible();
});

it('ontology authorization only queues the native worker and never uses a draft-merge action',async()=>{
 const value={...status('accepted'),ontology_id:'p',ontology_name:'Engineering ontology',artifact_sha256:'a'.repeat(64),authorization_valid:false,lifecycle_status:'approved',prefix:'eng'};
 apiClient.get.mockResolvedValue({data:value});
 render(<NativeChangeActions previewId="p" kind="publications"/>);
 await screen.findByRole('button',{name:'Authorize this ontology release'});
 expect(screen.queryByRole('button',{name:'Queue authorized graph publication'})).toBeNull();
 apiClient.post.mockResolvedValue({data:{...value,authorization_valid:true,change_request:{...value.change_request,state:'authorized'}}});
 review();fireEvent.click(screen.getByRole('button',{name:'Authorize this ontology release'}));
 await screen.findByRole('button',{name:'Queue authorized graph publication'});
 expect(screen.getByRole('button',{name:'Queue authorized graph publication'})).toBeDisabled();
 expect(apiClient.post.mock.calls[0][0]).toContain('/publications/p/request');
 expect(screen.queryByRole('button',{name:'Create authorized merged draft'})).toBeNull();
});

it('reviews and authorizes a retained workflow source-support revision',async()=>{
 const workflow=state=>({...status(state),operation:'revise',job_id:'semantic-source-validation',version:'1.0.0',authorization_valid:true});
 apiClient.get.mockResolvedValue({data:workflow('accepted')});
 apiClient.post.mockResolvedValue({data:workflow('authorized')});
 render(<NativeChangeActions previewId="p" kind="workflow_changes"/>);
 await screen.findByText('Request accepted; execution not authorized');review();
 fireEvent.click(screen.getByRole('button',{name:'Authorize workflow maintenance'}));
 expect(await screen.findByText('Workflow maintenance authorized')).toBeVisible();
 expect(screen.getByRole('button',{name:'Apply authorized workflow change'})).toBeDisabled();
 expect(apiClient.post.mock.calls[0][1].action).toBe('authorize');
});
