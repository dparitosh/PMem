import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { verifyStoredReadAccess, verifyStoredAccess, ACCESS_ATTEMPT_MS } from './readAccessVerification';
import { clearServiceAuthToken, getCredentialProfile, setCredentialProfile } from './serviceAuth';
vi.mock('../config', () => ({config:{semanticServiceUrls:{graph:'http://graph',ontology:'http://ontology'}},buildSemanticServiceUrl:(service,path)=>`http://${service}${path}`}));
beforeEach(() => { clearServiceAuthToken(); vi.stubGlobal('fetch',vi.fn()); });
afterEach(() => { clearServiceAuthToken(); vi.useRealTimers(); vi.unstubAllGlobals(); });

test('expired or missing access requires reconnection without a network write', async () => {
  expect((await verifyStoredReadAccess()).status).toBe('reconnect_required');
  expect(fetch).not.toHaveBeenCalled();
});

test('stored key is checked against each configured service with GET only', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
  fetch.mockResolvedValue({ok:true,status:200,json:async()=>({status:'authorized'})});
  expect((await verifyStoredReadAccess()).status).toBe('verified');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls.every(([url,options])=>url.endsWith('/auth/access') && options.headers.Authorization==='Bearer fixture-read-key' && !options.method)).toBe(true);
});

test('a transport failure does not erase a usable key or claim expiry', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
  fetch.mockRejectedValue(new TypeError('offline'));
  expect((await verifyStoredReadAccess()).status).toBe('unverified');
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('fixture-read-key');
});

test('revalidation checks maintenance independently with safe GET requests', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-read-key');
  setCredentialProfile('ADMIN_API_KEY', 'fixture-admin-key');
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'authorized' }) });
  const result = await verifyStoredAccess();
  expect(result.status).toBe('verified');
  expect(result.detail).toContain('Admin maintenance verified:');
  const calls = fetch.mock.calls.filter(([url]) => url.endsWith('/auth/admin-access'));
  expect(calls).toHaveLength(2);
  expect(calls.every(([, options]) => options.headers['X-API-Key'] === 'fixture-admin-key' && !options.headers.Authorization && !options.method)).toBe(true);
});

test('read success cannot hide rejected maintenance access', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-read-key');
  setCredentialProfile('ADMIN_API_KEY', 'fixture-admin-key');
  fetch.mockImplementation(async url => url.endsWith('/auth/admin-access')
    ? { ok: false, status: 403, json: async () => ({ detail: 'Invalid Admin key' }) }
    : { ok: true, status: 200, json: async () => ({ status: 'authorized' }) });
  const result = await verifyStoredAccess();
  expect(result.status).toBe('reconnect_required');
  expect(result.detail).toContain('Read access verified:');
  expect(result.message).toContain('Invalid Admin key');
});

test('read-only access stays verified without optional maintenance scope', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-read-key');
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'authorized' }) });
  const result = await verifyStoredAccess();
  expect(result.status).toBe('verified');
  expect(result.message).not.toContain('maintenance');
  expect(result.detail).toContain('Read access verified:');
  expect(fetch).toHaveBeenCalledTimes(2);
});

test('a slow service retries once without repeating successful services',async()=>{
 vi.useFakeTimers();setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
 let ontologyCalls=0;
 fetch.mockImplementation(url=>url.startsWith('http://ontology')&&++ontologyCalls===1?new Promise(()=>{}):Promise.resolve({ok:true,status:200,json:async()=>({status:'authorized'})}));
 const pending=verifyStoredReadAccess();
 await vi.advanceTimersByTimeAsync(ACCESS_ATTEMPT_MS+301);
 expect((await pending).status).toBe('verified');
 expect(fetch.mock.calls.filter(([url])=>url.startsWith('http://graph'))).toHaveLength(1);
 expect(ontologyCalls).toBe(2);
});
test('per-service timeouts retain partial verification and do not erase access',async()=>{
 vi.useFakeTimers();setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
 fetch.mockImplementation(url=>url.startsWith('http://ontology')?new Promise(()=>{}):Promise.resolve({ok:true,status:200,json:async()=>({status:'authorized'})}));
 const pending=verifyStoredReadAccess();await vi.advanceTimersByTimeAsync(ACCESS_ATTEMPT_MS*2+301);
 const result=await pending;
 expect(result.status).toBe('unverified');expect(result.message).toContain('1 of 2');expect(result.message).toContain('ontology: Verification timed out');
 expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('fixture-read-key');
});
test('authorization rejection is never retried',async()=>{
 setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
 fetch.mockResolvedValue({ok:false,status:403,json:async()=>({detail:'Access rejected'})});
 expect((await verifyStoredReadAccess()).status).toBe('reconnect_required');expect(fetch).toHaveBeenCalledTimes(2);
});
test('abort during transient backoff prevents retries',async()=>{
 vi.useFakeTimers();setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
 fetch.mockRejectedValue(new TypeError('offline'));const controller=new AbortController();
 const pending=verifyStoredReadAccess({signal:controller.signal});await vi.advanceTimersByTimeAsync(1);controller.abort();
 await pending;expect(fetch).toHaveBeenCalledTimes(2);
});
test('a replacement credential prevents retry of the old identity',async()=>{
 vi.useFakeTimers();setCredentialProfile('GRAPH_READ_TOKEN','fixture-read-key');
 fetch.mockRejectedValue(new TypeError('offline'));const pending=verifyStoredReadAccess();
 await vi.advanceTimersByTimeAsync(1);setCredentialProfile('GRAPH_READ_TOKEN','replacement');await vi.advanceTimersByTimeAsync(301);
 expect((await pending).status).toBe('unverified');expect(fetch).toHaveBeenCalledTimes(2);
});
