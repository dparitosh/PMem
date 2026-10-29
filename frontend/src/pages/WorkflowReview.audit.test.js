// Regression probes converted from the confirmed workflow audit defects.
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {vi,test,expect} from 'vitest';
import DataFlowPage from './DataFlowPage';
import {dataPipelineAPI,metadataRegistryAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({metadataRegistryAPI:{list:vi.fn()},dataPipelineAPI:{
 health:vi.fn().mockResolvedValue({data:{status:'configured'}}),
 telemetry:vi.fn().mockResolvedValue({data:{durable_job_telemetry:{runs:1}}}),
 runs:vi.fn().mockResolvedValue({data:{runs:[{run_id:'audit-run',job_id:'audit-job',status:'completed'}]}}),
 definitions:vi.fn().mockResolvedValue({data:{definitions:[]}}),
 replay:vi.fn(()=>new Promise(()=>{})),
}}));

test('Data Flow refreshes immediately after session replacement',async()=>{
 render(<DataFlowPage/>);await screen.findByText('configured');
 const before=dataPipelineAPI.runs.mock.calls.length;
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await waitFor(()=>expect(dataPipelineAPI.runs.mock.calls.length).toBeGreaterThan(before),{timeout:200});
});

test('rapid replay submission creates only one request',async()=>{
 render(<DataFlowPage/>);await screen.findByText('configured');
 const button=screen.getByRole('button',{name:'Replay',exact:true});
 const before=dataPipelineAPI.replay.mock.calls.length;
 act(()=>{fireEvent.click(button);fireEvent.click(button);});
 expect(dataPipelineAPI.replay.mock.calls.length-before).toBe(1);
});

test('a late approved-release response cannot restore old session choices',async()=>{
 let resolve;metadataRegistryAPI.list.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));
 render(<DataFlowPage/>);await screen.findByText('configured');
 fireEvent.click(screen.getByRole('tab',{name:'Approval & publication'}));
 fireEvent.click(screen.getByRole('button',{name:'Load approved semantic releases'}));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>resolve({data:{assets:[{asset_id:'old-release',version:'1',name:'Obsolete approval',lifecycle_status:'approved'}]}}));
 expect(screen.queryByRole('option',{name:/Obsolete approval/})).toBeNull();
});

test('an ambiguous replay retry reuses its submission identity',async()=>{
 dataPipelineAPI.replay.mockRejectedValueOnce(new Error('response lost'));
 render(<DataFlowPage/>);await screen.findByText('configured');
 fireEvent.click(screen.getByRole('button',{name:'Replay',exact:true}));
 await screen.findByText(/response lost/);
 const first=dataPipelineAPI.replay.mock.calls.at(-1)[1].idempotency_key;
 fireEvent.click(screen.getByRole('button',{name:'Replay',exact:true}));
 expect(dataPipelineAPI.replay.mock.calls.at(-1)[1].idempotency_key).toBe(first);
});

test('successful reconnect replaces an in-flight pre-reconnect load',async()=>{
 let resolveOld;
 dataPipelineAPI.runs.mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve;}));
 const before=dataPipelineAPI.runs.mock.calls.length;
 render(<DataFlowPage/>);
 await waitFor(()=>expect(dataPipelineAPI.runs.mock.calls.length).toBe(before+1));
 act(()=>window.dispatchEvent(new Event('depo:access-verified')));
 await waitFor(()=>expect(dataPipelineAPI.runs.mock.calls.length).toBe(before+2),{timeout:300});
 await screen.findByText('configured');
 await act(async()=>resolveOld({data:{runs:[{run_id:'obsolete-run',job_id:'obsolete-job'}]}}));
 expect(screen.queryByText('obsolete-job')).toBeNull();
});
