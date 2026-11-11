import React from 'react';
import {render,screen,fireEvent,waitFor,within,act} from '@testing-library/react';
import {vi} from 'vitest';
import DataFlowPage from './DataFlowPage';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{executionIdentity:vi.fn(),health:vi.fn(),telemetry:vi.fn(),runs:vi.fn(),definitions:vi.fn(),getRun:vi.fn(),replay:vi.fn()}}));
const a={run_id:'run-a',job_id:'job-a',job_name:'Job A',job_version:'1',status:'completed'},b={run_id:'run-b',job_id:'job-b',job_name:'Job B',job_version:'2',status:'completed'};
const definitions=[a,b].map(r=>({job_id:r.job_id,version:r.job_version,lifecycle_state:'approved',enabled:true}));
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();window.location.hash='';api.health.mockResolvedValue({data:{status:'configured'}});api.executionIdentity.mockResolvedValue({data:{actor:'pipeline-steward'}});api.telemetry.mockResolvedValue({data:{}});api.runs.mockResolvedValue({data:{runs:[a,b]}});api.definitions.mockResolvedValue({data:{definitions}});api.getRun.mockImplementation(id=>Promise.resolve({data:{...b,run_id:id}}));api.replay.mockResolvedValue({data:{run_manifest:{...b,run_id:'new-run',status:'queued',replay_of:'run-b'}}});});
afterEach(()=>{window.location.hash='';sessionStorage.clear();});
async function ready(){render(<DataFlowPage/>);await screen.findByRole('button',{name:'Job B'});}
function openReplay(){fireEvent.click(within(screen.getByRole('button',{name:'Job B'}).closest('tr')).getByRole('button',{name:'Replay'}));return screen.getByRole('dialog');}
function confirm(dialog){fireEvent.change(within(dialog).getByLabelText('Action approver'),{target:{value:'reviewer'}});fireEvent.click(within(dialog).getByRole('button',{name:'Confirm replay retained run'}));}
test('late detail response cannot replace a more recently selected run',async()=>{
 await ready();const detail=deferred();api.getRun.mockReturnValueOnce(detail.promise);window.location.hash='#/data-flow/old-run';
 fireEvent.click(screen.getByRole('button',{name:'Refresh'}));await waitFor(()=>expect(api.getRun).toHaveBeenCalledWith('old-run', expect.anything()));
 fireEvent.click(screen.getByRole('button',{name:'Job B'}));
 await act(async()=>detail.resolve({data:{...a,run_id:'old-run'}}));
 expect(within(screen.getByRole('complementary')).getByText('run-b')).toBeVisible();
});
test('successful mutation supersedes an in-flight polling read',async()=>{
 await ready();const older=deferred();api.runs.mockReturnValueOnce(older.promise);
 fireEvent.click(screen.getByRole('button',{name:'Refresh'}));await waitFor(()=>expect(api.runs).toHaveBeenCalledTimes(2));
 const dialog=openReplay();confirm(dialog);await within(dialog).findByText('Replay accepted');
 expect(api.runs).toHaveBeenCalledTimes(3);
 await act(async()=>older.resolve({data:{runs:[a]}}));
 expect(screen.getByRole('button',{name:'Job B'})).toBeVisible();
});
test('uncertain replay can recover its same receipt after the definition is disabled',async()=>{
 await ready();api.replay.mockRejectedValueOnce({response:{status:504,data:{detail:'Outcome unavailable'}}});
 const dialog=openReplay();confirm(dialog);await within(dialog).findByRole('alert');
 const key=api.replay.mock.calls[0][1].idempotency_key;
 api.definitions.mockResolvedValue({data:{definitions:definitions.map(d=>({...d,lifecycle_state:'disabled',enabled:false}))}});
 fireEvent(window,new Event('depo:access-verified'));await waitFor(()=>expect(api.runs).toHaveBeenCalledTimes(2));
 const retry=within(dialog).getByRole('button',{name:'Confirm replay retained run'});expect(retry).toBeEnabled();fireEvent.click(retry);
 await within(dialog).findByText('Replay accepted');expect(api.replay.mock.calls[1][1].idempotency_key).toBe(key);
 expect(api.replay).toHaveBeenCalledTimes(2);
});

test('authorization rejection after an uncertain attempt cannot replace its submission reference',async()=>{
 await ready();api.replay.mockRejectedValueOnce({response:{status:504,data:{detail:'Unknown outcome'}}})
 .mockRejectedValueOnce({response:{status:403,data:{detail:'Access temporarily unavailable'}}});
 let dialog=openReplay();confirm(dialog);await within(dialog).findByRole('alert');
 const key=api.replay.mock.calls[0][1].idempotency_key;
 fireEvent.click(within(dialog).getByRole('button',{name:'Confirm replay retained run'}));
 await within(dialog).findByText('Access temporarily unavailable');
 fireEvent.click(within(dialog).getByRole('button',{name:'Cancel'}));
 // A rejected credential blocks execution until access is revalidated (committed rule).
 act(()=>{fireEvent(window,new Event('depo:access-verified'));});
 dialog=openReplay();confirm(dialog);await within(dialog).findByText('Replay accepted');
 expect(api.replay.mock.calls.map(call=>call[1].idempotency_key)).toEqual([key,key,key]);
});
