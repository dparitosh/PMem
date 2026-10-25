import React, { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import useImportTaskTracking from './useImportTaskTracking';
const api = vi.hoisted(() => ({get:vi.fn()}));
vi.mock('../../../services/apiClient', () => ({apiClient:api}));
vi.mock('../../../config', () => ({API:{import:{status:'/tasks/:task_id',preview:'/preview/:task_id'}},buildUrl:p=>p,replaceParams:(p,v)=>p.replace(':task_id',v.task_id)}));
function Workspace() {
  const [status, setPipelineStatus] = useState({});
  const [previews, setPreviewsByTask] = useState({});
  const mounted = React.useRef(true);
  const tracking = useImportTaskTracking({isMountedRef:mounted,setPipelineStatus,setPreviewsByTask});
  return <><button onClick={()=>tracking.pollPipelineProgress('task','file')}>Resume</button>
    <button onClick={()=>tracking.clearPoller('task:file')}>Stop view</button>
    <output>{status.file?.message || 'No status'}</output><output>{JSON.stringify(previews)}</output></>;
}
beforeEach(()=>{vi.useFakeTimers();api.get.mockReset();});
afterEach(()=>vi.useRealTimers());
test('stale completion cannot cancel a new poller for the same retained task', async()=>{
  const reads=[];
  api.get.mockImplementation((url,options)=>new Promise(resolve=>reads.push({resolve,options})));
  render(<Workspace/>);
  fireEvent.click(screen.getByText('Resume'));
  await act(async()=>vi.advanceTimersByTimeAsync(0));
  fireEvent.click(screen.getByText('Stop view'));
  expect(reads[0].options.signal.aborted).toBe(true);
  fireEvent.click(screen.getByText('Resume'));
  await act(async()=>vi.advanceTimersByTimeAsync(0));
  await act(async()=>reads[0].resolve({data:{status:'running',message:'Stale task'}}));
  expect(reads[1].options.signal.aborted).toBe(false);
  expect(screen.queryByText('Stale task')).not.toBeInTheDocument();
  await act(async()=>reads[1].resolve({data:{status:'running',message:'Current task'}}));
  expect(screen.getByText('Current task')).toBeVisible();
});
test('schema cleanup aborts the first read and prevents a late history update', async()=>{
  let resolveRead,signal;
  api.get.mockImplementation((url,options)=>{signal=options.signal;return new Promise(resolve=>{resolveRead=resolve;});});
  render(<Workspace/>);
  fireEvent.click(screen.getByText('Resume'));
  await act(async()=>vi.advanceTimersByTimeAsync(0));
  act(()=>window.dispatchEvent(new Event('dt-schema-cleaned')));
  expect(signal.aborted).toBe(true);
  await act(async()=>resolveRead({data:{status:'running',message:'Deleted history'}}));
  expect(screen.getByText('No status')).toBeVisible();
  expect(screen.queryByText('Deleted history')).not.toBeInTheDocument();
});

test('an aborted preview cannot stop the replacement poller for the same task', async()=>{
  const reads=[];
  api.get.mockImplementation((url,options)=>new Promise((resolve,reject)=>reads.push({url,options,resolve,reject})));
  render(<Workspace/>);
  fireEvent.click(screen.getByText('Resume'));
  await act(async()=>vi.advanceTimersByTimeAsync(0));
  await act(async()=>reads[0].resolve({data:{status:'ready_for_commit',current_stage:'preview'}}));
  expect(reads[1].url).toBe('/preview/task');
  fireEvent.click(screen.getByText('Stop view'));
  fireEvent.click(screen.getByText('Resume'));
  await act(async()=>vi.advanceTimersByTimeAsync(0));
  await act(async()=>reads[1].reject(Object.assign(new Error('Aborted'),{name:'AbortError'})));
  expect(reads[2].options.signal.aborted).toBe(false);
});
