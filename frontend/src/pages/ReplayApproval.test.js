import React from 'react';
import {render,screen,fireEvent,waitFor,within} from '@testing-library/react';
import {vi} from 'vitest';
import DataFlowPage from './DataFlowPage';
import {setCredentialProfile} from '../services/serviceAuth';
import {dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{executionIdentity:vi.fn().mockResolvedValue({data:{actor:'ui-user'}}),health:vi.fn().mockResolvedValue({data:{status:'configured'}}),telemetry:vi.fn().mockResolvedValue({data:{}}),runs:vi.fn(),definitions:vi.fn().mockResolvedValue({data:{definitions:[]}}),replay:vi.fn(),getRun:vi.fn()}}));
const a={run_id:'run-a',job_id:'job-a',job_name:'Job A',job_version:'1',status:'completed',source_standard:'ap242',source_system:'system-a',input_manifest:{record_count:10,payload_digest:'digest-a'}};
const b={run_id:'run-b',job_id:'job-b',job_name:'Job B',job_version:'2',status:'failed',source_standard:'sysml-v1',source_system:'system-b',input_manifest:{record_count:1288,payload_digest:'digest-b'}};
beforeEach(()=>{
 sessionStorage.clear();
 dataPipelineAPI.definitions.mockReset().mockResolvedValue({data:{definitions:[a,b].map(run=>({job_id:run.job_id,version:run.job_version,lifecycle_state:'approved',enabled:true}))}});
 dataPipelineAPI.replay.mockReset().mockImplementation(id=>Promise.resolve({data:{run_manifest:{...b,run_id:'new-run',replay_of:id,status:'queued'}}}));
 dataPipelineAPI.runs.mockReset().mockResolvedValue({data:{runs:[a,b]}});
 dataPipelineAPI.getRun.mockReset().mockImplementation(id=>Promise.resolve({data:id==='new-run'?{...b,run_id:id,status:'queued'}:id==='run-b'?b:a}));
 setCredentialProfile('DATA_JOB_EXECUTION_TOKEN','');window.location.hash='';
});
afterEach(()=>{setCredentialProfile('DATA_JOB_EXECUTION_TOKEN','');window.location.hash='';});
async function openB(){
 render(<DataFlowPage/>);await screen.findByText('configured');await screen.findByRole('button',{name:'Job B'});
 const row=screen.getByRole('button',{name:'Job B'}).closest('tr');
 fireEvent.click(within(row).getByRole('button',{name:'Replay'}));
 return screen.getByRole('dialog',{name:'Replay retained run'});
}
function confirm(dialog){fireEvent.change(within(dialog).getByLabelText('Action approver'),{target:{value:'reviewer'}});fireEvent.click(within(dialog).getByRole('button',{name:'Confirm replay retained run'}));}

test('review identifies the clicked row before any request and cancel never replays',async()=>{
 const dialog=await openB();
 expect(within(dialog).getByText('Job B')).toBeVisible();
 for(const text of ['job-b','run-b','2','system-b','sysml-v1','1288','digest-b'])expect(within(dialog).getByText(text)).toBeVisible();
 expect(within(dialog).queryByText('run-a')).toBeNull();
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
 fireEvent.click(within(dialog).getByRole('button',{name:'Cancel'}));
 expect(screen.queryByRole('dialog')).toBeNull();expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});

test('missing approver blocks confirmation and accepted replay retains both original and new IDs',async()=>{
 setCredentialProfile('DATA_JOB_EXECUTION_TOKEN','synthetic-key');
 const dialog=await openB();
 expect(within(dialog).getByRole('button',{name:'Confirm replay retained run'})).toBeDisabled();
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
 confirm(dialog);
 await waitFor(()=>expect(dataPipelineAPI.replay).toHaveBeenCalledWith('run-b',expect.objectContaining({approved_by:'reviewer',idempotency_key:expect.any(String)})));
 expect(await within(dialog).findByText('Replay accepted')).toBeVisible();
 expect(within(dialog).getByText('run-b')).toBeVisible();expect(within(dialog).getByText('new-run')).toBeVisible();
 expect(within(dialog).getByRole('link',{name:'Open resulting run'})).toHaveAttribute('href','#/data-flow/new-run');
 expect(screen.getByRole('status',{name:'Last action result'})).toHaveTextContent('original run run-b');
});

test('failed replay retains row identity and retry reuses its submission key after background refresh',async()=>{
 dataPipelineAPI.replay.mockRejectedValueOnce({response:{status:503,data:{detail:'Response not confirmed'}}});
 const dialog=await openB();confirm(dialog);
 await within(dialog).findByRole('alert');
 const key=dataPipelineAPI.replay.mock.calls[0][1].idempotency_key;
 dataPipelineAPI.runs.mockResolvedValue({data:{runs:[a]}});
 fireEvent(window,new Event('depo:access-verified'));
 await waitFor(()=>expect(dataPipelineAPI.runs).toHaveBeenCalledTimes(2));
 expect(within(dialog).getByText('run-b')).toBeVisible();
 fireEvent.click(within(dialog).getByRole('button',{name:'Confirm replay retained run'}));
 await waitFor(()=>expect(dataPipelineAPI.replay).toHaveBeenCalledTimes(2));
 expect(dataPipelineAPI.replay.mock.calls[1][0]).toBe('run-b');
 expect(dataPipelineAPI.replay.mock.calls[1][1].idempotency_key).toBe(key);
});

test('credential change closes the action context without submitting',async()=>{
 await openB();fireEvent(window,new Event('depo:credentials-cleared'));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});

 test('run search includes its visible job name and source system',async()=>{
 render(<DataFlowPage/>);await screen.findByText('configured');await screen.findByRole('button',{name:'Job B'});
 fireEvent.change(screen.getByLabelText('Find a run'),{target:{value:'Job B'}});
 expect(screen.getByRole('button',{name:'Job B'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Job A'})).toBeNull();
 fireEvent.change(screen.getByLabelText('Find a run'),{target:{value:'system-a'}});
 expect(screen.getByRole('button',{name:'Job A'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Job B'})).toBeNull();
 });

test.each([['draft',true],['disabled',false],['approved',false]])('blocked definition %s / enabled %s cannot submit and links to the exact version',async(state,enabled)=>{
 dataPipelineAPI.definitions.mockResolvedValue({data:{definitions:[{job_id:b.job_id,version:b.job_version,lifecycle_state:state,enabled}]}});
 const dialog=await openB();
 expect(within(dialog).getByText('Replay unavailable')).toBeVisible();
 expect(within(dialog).getByRole('button',{name:'Confirm replay retained run'})).toBeDisabled();
 fireEvent.click(within(dialog).getByRole('button',{name:'Review job definition'}));
 expect(screen.getByRole('tab',{name:'Pipeline jobs'})).toHaveAttribute('aria-selected','true');
 expect(screen.getByText(/Selected job: job-b/)).toHaveTextContent('Version: 2');
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});
test('definition disabled after opening review is rechecked before replay',async()=>{
 const dialog=await openB();
 dataPipelineAPI.definitions.mockResolvedValue({data:{definitions:[{job_id:b.job_id,version:b.job_version,lifecycle_state:'disabled',enabled:false}]}});
 confirm(dialog);await within(dialog).findByRole('alert');
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
 expect(within(dialog).getByText('run-b')).toBeVisible();
 expect(within(dialog).queryByRole('button',{name:'Confirm replay retained run'})).toBeNull();
});
test('a different approved version does not authorize replay of the old version',async()=>{
 dataPipelineAPI.definitions.mockResolvedValue({data:{definitions:[{job_id:b.job_id,version:'3',lifecycle_state:'approved',enabled:true}]}});
 const dialog=await openB();
 expect(within(dialog).getByText('Replay unavailable')).toBeVisible();
 expect(within(dialog).getByRole('button',{name:'Confirm replay retained run'})).toBeDisabled();
 expect(dataPipelineAPI.replay).not.toHaveBeenCalled();
});

test('server lifecycle rejection is not offered as a blind retry',async()=>{
 dataPipelineAPI.replay.mockRejectedValueOnce({response:{status:409,data:{detail:'Only an approved and enabled data-job definition can be replayed'}}});
 const dialog=await openB();confirm(dialog);await within(dialog).findByRole('alert');
 expect(within(dialog).getByText('run-b')).toBeVisible();
 expect(within(dialog).queryByRole('button',{name:'Confirm replay retained run'})).toBeNull();
 expect(within(dialog).getByRole('button',{name:'Review job definition'})).toBeVisible();
 expect(within(dialog).queryByText(/Retry reuses/)).toBeNull();
 expect(dataPipelineAPI.replay).toHaveBeenCalledOnce();
});
