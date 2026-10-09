import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { verifyStoredReadAccess, verifyStoredAccess } from './readAccessVerification';
import { clearServiceAuthToken, getCredentialProfile, setCredentialProfile } from './serviceAuth';
vi.mock('../config', () => ({config:{semanticServiceUrls:{graph:'http://graph',ontology:'http://ontology'}},buildSemanticServiceUrl:(service,path)=>`http://${service}${path}`}));
beforeEach(() => { clearServiceAuthToken(); vi.stubGlobal('fetch',vi.fn()); });
afterEach(() => { clearServiceAuthToken(); vi.unstubAllGlobals(); });

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
  expect(result.message).toContain('Admin maintenance verified:');
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
  expect(result.message).toContain('Read access verified:');
  expect(result.message).toContain('Invalid Admin key');
});

test('read-only revalidation explicitly reports missing maintenance scope', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'fixture-read-key');
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'authorized' }) });
  expect((await verifyStoredAccess()).message).toContain('Admin maintenance is not connected');
  expect(fetch).toHaveBeenCalledTimes(2);
});
