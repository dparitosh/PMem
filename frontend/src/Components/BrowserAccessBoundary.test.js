import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import BrowserAccessBoundary from './BrowserAccessBoundary';
import { getBrowserSessionStatus, installBrowserSession, renewBrowserSession } from '../services/serviceAuth';
vi.mock('../services/serviceAuth',()=>({getBrowserSessionStatus:vi.fn(),installBrowserSession:vi.fn(),renewBrowserSession:vi.fn()}));
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks();getBrowserSessionStatus.mockReturnValue(null);});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();});
const response=body=>({ok:true,json:async()=>body});

test('failed local bootstrap holds service-reading children until reconnect succeeds',async()=>{
  const mounted=vi.fn();
  function Workspace(){React.useEffect(()=>{mounted();},[]);return <div>Protected workspace</div>;}
  const fetch=vi.fn().mockResolvedValueOnce(response({mode:'local'}))
    .mockResolvedValueOnce({ok:false,json:async()=>({detail:'Local session authority is unavailable.'})})
    .mockResolvedValueOnce(response({mode:'local'}))
    .mockResolvedValueOnce(response({token:'depo_session_recovered'}));
  vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><Workspace/></BrowserAccessBoundary>);
  const reconnect=await screen.findByRole('button',{name:'Reconnect local access'});
  expect(mounted).not.toHaveBeenCalled();
  expect(screen.queryByText('Protected workspace')).not.toBeInTheDocument();
  fireEvent.click(reconnect);
  await screen.findByText('Protected workspace');
  expect(mounted).toHaveBeenCalledTimes(1);
  expect(installBrowserSession).toHaveBeenCalledWith({token:'depo_session_recovered'});
});

test('local credential expiry reconnects promptly without waiting for the interval',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response({mode:'local'}))
    .mockResolvedValueOnce(response({token:'depo_session_old'}))
    .mockResolvedValueOnce(response({token:'depo_session_new'}));
  vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');
  fireEvent(window,new Event('depo:session-expired'));
  await waitFor(()=>expect(installBrowserSession).toHaveBeenCalledWith({token:'depo_session_new'}));
  expect(fetch.mock.calls.map(([path])=>path)).toEqual(['/_pmem-local/config','/_pmem-local/session','/_pmem-local/session']);
});

test('expiry does not reconnect after explicit local sign-out',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockResolvedValueOnce(response({token:'depo_session_old'}));
  vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');
  fireEvent(window,new Event('depo:credentials-cleared'));
  fireEvent(window,new Event('depo:session-expired'));
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,10));});
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(screen.getByText('Local access is disconnected.')).toBeInTheDocument();
});
test('manual deployments do not bootstrap on startup or visibility changes',async()=>{
  const fetch=vi.fn().mockResolvedValue(response({mode:'manual'}));vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');fireEvent(document,new Event('visibilitychange'));
  expect(fetch).toHaveBeenCalledTimes(1);expect(installBrowserSession).not.toHaveBeenCalled();
});
test('local startup exchanges only same-origin cookies and installs a delegated session',async()=>{
  const body={token:'depo_session_opaque',profiles:['GRAPH_READ_TOKEN']};
  const fetch=vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockResolvedValueOnce(response(body));vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');expect(installBrowserSession).toHaveBeenCalledWith(body);
  expect(fetch.mock.calls[1][0]).toBe('/_pmem-local/session');
  expect(fetch.mock.calls[1][1]).toMatchObject({credentials:'same-origin',redirect:'error',body:'{}'});
  expect(fetch.mock.calls[1][1].headers.Authorization).toBeUndefined();
});
test('explicit sign-out remains disconnected after refresh until reconnect is requested',async()=>{
  sessionStorage.setItem('depo.localAccessDisconnected','true');
  const fetch=vi.fn().mockResolvedValue(response({mode:'local'}));vi.stubGlobal('fetch',fetch);
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Local access is disconnected.');expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button',{name:'Reconnect local access'})).toBeInTheDocument();
});
test('late bootstrap cannot undo sign-out',async()=>{
  let finish;const pending=new Promise(resolve=>{finish=resolve;});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockReturnValueOnce(pending));
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
  fireEvent(window,new Event('depo:credentials-cleared'));
  await act(async()=>{finish(response({token:'depo_session_late'}));});
  expect(installBrowserSession).not.toHaveBeenCalled();
});
test('only visible local tabs renew near-expiry delegates',async()=>{
  let tick;
  vi.spyOn(globalThis,'setInterval').mockImplementation(callback=>{tick=callback;return 1;});
  vi.spyOn(globalThis,'clearInterval').mockImplementation(()=>{});
  const visibility=vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockResolvedValueOnce(response({token:'depo_session_opaque'})));
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');
  getBrowserSessionStatus.mockReturnValue({expiresAt:new Date(Date.now()+60000).toISOString()});
  await act(async()=>{await tick();});expect(renewBrowserSession).toHaveBeenCalledTimes(1);
  visibility.mockReturnValue('hidden');await act(async()=>{await tick();});
  expect(renewBrowserSession).toHaveBeenCalledTimes(1);
  fireEvent(window,new Event('depo:credentials-cleared'));visibility.mockReturnValue('visible');
  await act(async()=>{await tick();});expect(renewBrowserSession).toHaveBeenCalledTimes(1);
});


test('body reads retain the request deadline after response headers arrive',async()=>{
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']});
  let sessionSignal;
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockImplementationOnce(async(_path,options)=>{
    sessionSignal=options.signal;
    return {ok:true,json:()=>new Promise((_resolve,reject)=>sessionSignal.addEventListener('abort',()=>reject(new Error('body aborted'))))};
  }));
  const view=render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await waitFor(()=>expect(sessionSignal).toBeDefined());
  expect(sessionSignal.aborted).toBe(false);
  await act(async()=>{await vi.advanceTimersByTimeAsync(20000);});
  expect(sessionSignal.aborted).toBe(true);
  await act(async()=>{view.unmount();});
  expect(installBrowserSession).not.toHaveBeenCalled();
});

test('late renewal failure preserves explicit disconnected status',async()=>{
  let tick, fail;
  vi.spyOn(globalThis,'setInterval').mockImplementation(callback=>{tick=callback;return 1;});
  vi.spyOn(globalThis,'clearInterval').mockImplementation(()=>{});
  vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(response({mode:'local'})).mockResolvedValueOnce(response({token:'depo_session_opaque'})));
  render(<BrowserAccessBoundary><div>Workspace</div></BrowserAccessBoundary>);
  await screen.findByText('Workspace');
  getBrowserSessionStatus.mockReturnValue({expiresAt:new Date(Date.now()+60000).toISOString()});
  renewBrowserSession.mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}));
  let pending;act(()=>{pending=tick();});
  fireEvent(window,new Event('depo:credentials-cleared'));
  await act(async()=>{fail(new Error('authority unavailable'));await pending;});
  expect(screen.getByText('Local access is disconnected.')).toBeInTheDocument();
});
