import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import {vi,beforeEach,test,expect} from 'vitest';
import ReleaseChangePanel from './ReleaseChangePanel';
import {apiClient} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),post:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(_service,path)=>path}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'coordinator-token',publicationRecoveryScope:()=> 'deployment-a'}));
vi.mock('./NativeChangeActions',()=>({default:({kind,executionBlockedReason,onChanged})=><section aria-label={`Native ${kind}`}><p>{executionBlockedReason||'Native step available'}</p><button onClick={()=>onChanged()}>Refresh {kind}</button></section>}));
const configuration='a'.repeat(64);
const record=(state='submitted')=>({request_id:'release-a',title:'Engineering release',state,revision:1,configuration_id:configuration,configuration_context:'/oslc/change-control/configurations/'+configuration,source_run_id:'run-a',scope_changed:false,tracking_changed:false,history:[],configuration:{selections:{source:{accepted_sha256:'b'.repeat(64)}}},operations:[{source_kind:'pipeline',identifier:'run-a',preview_id:'run-a',state:'submitted',receipt_verified:false},{source_kind:'product_changes',identifier:'product:1',preview_id:'product:1',state:'submitted',receipt_verified:false}]});
beforeEach(()=>vi.resetAllMocks());

test('selects named source and ordered native requests without entering identifiers',async()=>{
 const onCreated=vi.fn();apiClient.post.mockResolvedValue({data:record()});
 render(<ReleaseChangePanel records={[{source_kind:'pipeline',identifier:'run-a',title:'Imported engineering records',type:'oslc_cm:ChangeRequest',change_state:'submitted',release_source_ready:true,reference:'RUN-2026-000101'},{source_kind:'product_changes',identifier:'product:1',title:'Engineering data product',type:'oslc_cm:ChangeRequest',change_state:'submitted'}]} onCreated={onCreated}/>);
 fireEvent.click(screen.getByText('Plan one source-to-release change'));
 fireEvent.change(screen.getByLabelText('Change title'),{target:{value:'Engineering release'}});
 fireEvent.change(screen.getByLabelText('Business reason'),{target:{value:'Publish reviewed source evidence'}});
 fireEvent.change(screen.getByLabelText('Retained source run'),{target:{value:'run-a'}});
 fireEvent.click(screen.getByLabelText(/Imported engineering records/));
 fireEvent.click(screen.getByLabelText(/Product release · Engineering data product/));
 fireEvent.click(screen.getByRole('button',{name:'Submit source-to-release change'}));
 await waitFor(()=>expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({request_id:'release-a'})));
 expect(apiClient.post.mock.calls[0][1]).toEqual({title:'Engineering release',reason:'Publish reviewed source evidence',source_run_id:'run-a',operations:[{source_kind:'pipeline',identifier:'run-a'},{source_kind:'product_changes',identifier:'product:1'}]});
 expect(apiClient.post.mock.calls[0][0]).not.toContain('/execute');
});

test('acceptance requires new consent and includes exact baseline without caller identity',async()=>{
 apiClient.get.mockResolvedValue({data:record()});apiClient.post.mockResolvedValue({data:record('accepted')});
 render(<ReleaseChangePanel requestId="release-a"/>);
 const button=await screen.findByRole('button',{name:'Accept source-to-release request'});expect(button).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(button);
 await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(1));
 expect(apiClient.post.mock.calls[0][1]).toEqual({action:'accept',expected_revision:1,configuration_id:configuration,reason:''});
 expect(apiClient.post.mock.calls[0][2].headers['Configuration-Context']).toBe('/oslc/change-control/configurations/'+configuration);
});

test('parent authorization does not bypass native permissions or prerequisite receipts',async()=>{
 apiClient.get.mockResolvedValue({data:record('authorized')});
 render(<ReleaseChangePanel requestId="release-a"/>);
 await screen.findByText('Native step available');
 expect(screen.getByRole('region',{name:'Native pipeline'})).toHaveTextContent('Native step available');
 fireEvent.click(screen.getByRole('button',{name:'Review operation 2'}));
 expect(screen.getByRole('region',{name:'Native product_changes'})).toHaveTextContent('Complete and verify');
 expect(apiClient.post).not.toHaveBeenCalled();
});

test('credential replacement ignores late decision responses and clears consent',async()=>{
 apiClient.get.mockResolvedValue({data:record()});let finish;apiClient.post.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const onChanged=vi.fn();
 render(<ReleaseChangePanel requestId="release-a" onChanged={onChanged}/>);
 await screen.findByRole('button',{name:'Accept source-to-release request'});
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Accept source-to-release request'}));
 fireEvent(window,new Event('depo:credentials-cleared'));
 await act(async()=>finish({data:record('accepted')}));
 expect(onChanged).not.toHaveBeenCalled();
 expect(screen.getByRole('checkbox')).not.toBeChecked();
});

test('malformed native scope is an explicit error instead of a rendering failure',async()=>{
 apiClient.get.mockResolvedValue({data:{...record(),operations:[null]}});
 render(<ReleaseChangePanel requestId="release-a"/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Release scope could not be verified');
});


test('planner excludes terminal requests and unprepared source runs and links to owning pages',()=>{
 render(<ReleaseChangePanel records={[
  {source_kind:'pipeline',identifier:'old',title:'Old published run',type:'oslc_cm:ChangeRequest',change_state:'executed',release_source_ready:true},
  {source_kind:'pipeline',identifier:'unready',title:'Unready source',type:'oslc_cm:ChangeRequest',change_state:'submitted',release_source_ready:false},
  {source_kind:'product_changes',identifier:'old-product',title:'Published product',type:'oslc_cm:ChangeRequest',change_state:'executed'}
 ]}/>);
 fireEvent.click(screen.getByText('Plan one source-to-release change'));
 expect(screen.queryByRole('option',{name:/Old published run/})).not.toBeInTheDocument();
 expect(screen.queryByRole('option',{name:/Unready source/})).not.toBeInTheDocument();
 expect(screen.queryByRole('checkbox',{name:/Published product/})).not.toBeInTheDocument();
 expect(screen.queryByRole('checkbox',{name:/Unready source/})).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Data Flow'})).toHaveAttribute('href','#/data-flow?view=runs');
 expect(screen.getByRole('link',{name:'Data Products'})).toHaveAttribute('href','#/data-products?view=governance');
 expect(screen.getByRole('button',{name:'Submit source-to-release change'})).toBeDisabled();
});

test('planner distinguishes identical source names and requires the selected source plus final product',()=>{
 const rows=[
  {source_kind:'pipeline',identifier:'a',title:'Same source',type:'oslc_cm:ChangeRequest',change_state:'submitted',release_source_ready:true,reference:'RUN-2026-000101',request_number:'CR-2026-000101'},
  {source_kind:'pipeline',identifier:'b',title:'Same source',type:'oslc_cm:ChangeRequest',change_state:'authorized',release_source_ready:true,reference:'RUN-2026-000102',request_number:'CR-2026-000102'},
  {source_kind:'product_changes',identifier:'p:1',title:'Product',type:'oslc_cm:ChangeRequest',change_state:'submitted',request_number:'CR-2026-000103'}
 ];
 render(<ReleaseChangePanel records={rows}/>);fireEvent.click(screen.getByText('Plan one source-to-release change'));
 expect(screen.getByRole('option',{name:'RUN-2026-000101 · Same source'})).toBeInTheDocument();
 expect(screen.getByRole('option',{name:'RUN-2026-000102 · Same source'})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Change title'),{target:{value:'Release'}});
 fireEvent.change(screen.getByLabelText('Business reason'),{target:{value:'Review retained records'}});
 fireEvent.change(screen.getByLabelText('Retained source run'),{target:{value:'a'}});
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000102/}));
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000103/}));
 expect(screen.getByRole('button',{name:'Submit source-to-release change'})).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000102/}));
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000103/}));
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000101/}));
 fireEvent.click(screen.getByRole('checkbox',{name:/CR-2026-000103/}));
 expect(screen.getByRole('button',{name:'Submit source-to-release change'})).toBeEnabled();
 fireEvent.change(screen.getByLabelText('Retained source run'),{target:{value:'b'}});
 expect(screen.getByRole('button',{name:'Submit source-to-release change'})).toBeDisabled();
});

test('completed release retains verified delivery',async()=>{
 const value=record('completed');value.operations=value.operations.map(step=>({...step,state:'executed',receipt_verified:true}));apiClient.get.mockResolvedValue({data:value});render(<ReleaseChangePanel requestId="release-a"/>);
 await screen.findByText('Release completed; retained evidence is read-only.');expect(screen.getAllByText('Delivery verified for this release.')).toHaveLength(2);expect(screen.queryByText(/Final verification required/)).not.toBeInTheDocument();
});
test('loading does not claim preparation history is empty',()=>{
 render(<ReleaseChangePanel loading/>);fireEvent.click(screen.getByText('Plan one source-to-release change'));expect(screen.getByRole('status')).toHaveTextContent('Loading prepared requests');expect(screen.queryByRole('link',{name:'Data Flow'})).not.toBeInTheDocument();expect(screen.getByLabelText('Retained source run')).toBeDisabled();
});
