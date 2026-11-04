// Regression checks for the session lifecycle audit.
import {afterEach,expect,test,vi} from 'vitest';
import {installBrowserSession,renewBrowserSession,getCredentialProfile,clearServiceAuthToken} from './serviceAuth';
import {prepareSessionRequest,trackSessionRequest,releaseRequest} from './requestSession';
vi.mock('../config',()=>({config:{semanticServiceUrls:{ontology:'http://vm:8011'}},buildSemanticServiceUrl:(_s,p)=>'http://vm:8011'+p}));
const body=token=>({token,profiles:['GRAPH_READ_TOKEN'],expires_at:new Date(Date.now()+120000).toISOString(),absolute_expires_at:new Date(Date.now()+3600000).toISOString()});
afterEach(()=>{clearServiceAuthToken(false);vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});

test('RCA-01: a new session gets an independent renewal flight',async()=>{
 const finishes=[];
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(resolve=>{finishes.push(resolve);})));
 installBrowserSession(body('depo_session_old'));
 const oldFlight=renewBrowserSession();
 installBrowserSession(body('depo_session_new'));
 const newFlight=renewBrowserSession();
 const calls=fetch.mock.calls.length;
 finishes[0]({ok:true,json:async()=>body('depo_session_old')});
 expect(await oldFlight).toBeNull();
 const sharedNewFlight=renewBrowserSession();
 expect(fetch).toHaveBeenCalledTimes(2);
 finishes[1]({ok:true,json:async()=>body('depo_session_new')});
 expect(await newFlight).not.toBeNull();
 expect(await sharedNewFlight).not.toBeNull();
 expect(calls).toBe(2);
 expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_new');
});

test('RCA-02: equal-millisecond old logout cannot clear a replacement session',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-04T00:00:00Z'));
 const sentAt=Date.now();
 installBrowserSession(body('depo_session_new'));
 const scope=JSON.stringify(['',[['ontology','http://vm:8011']]]);
 window.dispatchEvent(new StorageEvent('storage',{key:'depo.sessionSignal.v1',newValue:JSON.stringify({action:'logout',scope,sentAt})}));
 expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_new');
});

test('RCA-03: completion detaches caller listeners and retries restore cancellation',()=>{
 const parent=new AbortController();
 const add=vi.spyOn(parent.signal,'addEventListener');
 const remove=vi.spyOn(parent.signal,'removeEventListener');
 const config=prepareSessionRequest({signal:parent.signal});
 trackSessionRequest(config);releaseRequest(config);
 expect(add).toHaveBeenCalledWith('abort',expect.any(Function),expect.any(Object));
 expect(remove).toHaveBeenCalledWith('abort',expect.any(Function));
 expect(config.__credentialController.signal.aborted).toBe(false);
 prepareSessionRequest(config);trackSessionRequest(config);
 parent.abort();
 expect(config.signal.aborted).toBe(true);
 releaseRequest(config);
});

test('reconnect aborts a request during retry backoff and releases caller listeners',()=>{
 const parent=new AbortController();
 const remove=vi.spyOn(parent.signal,'removeEventListener');
 const request=prepareSessionRequest({signal:parent.signal});
 trackSessionRequest(request);
 releaseRequest(request,true);
 window.dispatchEvent(new Event('depo:session-replaced'));
 expect(request.signal.aborted).toBe(true);
 releaseRequest(request);
 expect(remove).toHaveBeenCalledWith('abort',expect.any(Function));
});

test('repeated completed reads leave no caller abort listeners attached',()=>{
 const parent=new AbortController();
 const listeners=new Set();
 const add=parent.signal.addEventListener.bind(parent.signal);
 const remove=parent.signal.removeEventListener.bind(parent.signal);
 vi.spyOn(parent.signal,'addEventListener').mockImplementation((event,callback,options)=>{listeners.add(callback);add(event,callback,options);});
 vi.spyOn(parent.signal,'removeEventListener').mockImplementation((event,callback)=>{listeners.delete(callback);remove(event,callback);});
 for(let index=0;index<10000;index++){
   const request=prepareSessionRequest({signal:parent.signal});
   trackSessionRequest(request);releaseRequest(request);
 }
 expect(listeners.size).toBe(0);
 expect(parent.signal.aborted).toBe(false);
});

test('corrupt non-secret session clock cannot poison logout ordering',()=>{
 localStorage.setItem('depo.sessionClock.v1','Infinity');
 installBrowserSession(body('depo_session_clock'));
 expect(Number.isSafeInteger(Number(localStorage.getItem('depo.sessionClock.v1')))).toBe(true);
});
