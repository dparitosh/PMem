import { clearClientSessionId, getClientSessionId, setClientSessionId } from './apiClient';
import apiClient from './apiClient';
import { platformAPI } from './apiClient';
import { vi } from 'vitest';
vi.unmock('axios');
import { AxiosHeaders } from 'axios';
import { buildUrl } from '../config';
import { clearServiceAuthToken, setCredentialProfile } from './serviceAuth';

test('shell pipeline readiness is independent of optional Spark configuration', async () => {
  const get = vi.spyOn(apiClient, 'get').mockResolvedValue({data:{status:'ready'}});
  try {
    await platformAPI.health('dataPipeline');
    expect(get.mock.calls[0][0]).toMatch(/\/readyz$/);
  } finally { get.mockRestore(); }
});

test.each([
  [{status:'ok'}, true], [{status:'ready'}, true], [{status:'degraded'}, false],
  [{}, false], ['<html>proxy error</html>', false], [{status:'unavailable'}, false],
])('health requires a recognized positive service status: %j', async (data, expected) => {
  const health = vi.spyOn(platformAPI, 'health').mockResolvedValue({data});
  try {
    const result = await platformAPI.coreHealth();
    expect(Object.values(result)).toHaveLength(10);
    expect(Object.values(result).every(value => value === expected)).toBe(true);
  } finally { health.mockRestore(); }
});

test('pipeline errors preserve diagnostic and recovery identities', async () => {
  const receive = vi.fn();
  window.addEventListener('depo:run-recovery', receive);
  const failure = { message:'failed', config:{url:buildUrl('/api/v1/pipeline/jobs/runs/retained/reconcile-analytics'),method:'post'},
    response:{status:503,headers:{'x-request-id':'request-123','x-depo-run-id':'retained','x-depo-run-kind':'pipeline'},data:{detail:'Storage unavailable'}} };
  try {
    await expect(apiClient.interceptors.response.handlers[0].rejected(failure)).rejects.toBe(failure);
    expect(failure.apiError.requestId).toBe('request-123');
    expect(failure.apiError.message).toBe('Storage unavailable Request ID: request-123');
    expect(receive.mock.calls[0][0].detail).toEqual({runId:'retained',kind:'pipeline'});
  } finally { window.removeEventListener('depo:run-recovery', receive); }
});

test.each([
  { 'X-API-Key': 'explicit-admin-key' },
  { 'x-api-key': 'explicit-admin-key' },
  new AxiosHeaders({ 'X-API-Key': 'explicit-admin-key' }),
])('Admin interceptor preserves an explicit credential', headers => {
  clearServiceAuthToken();
  setCredentialProfile('ADMIN_API_KEY', 'stored-admin-key');
  try {
    const result = apiClient.interceptors.request.handlers[0].fulfilled({ url: buildUrl('/api/v1/admin/health', 'get'), method: 'get', headers });
    const key = result.headers.get?.('X-API-Key') || Object.entries(result.headers).find(([name]) => name.toLowerCase() === 'x-api-key')?.[1];
    expect(key).toBe('explicit-admin-key');
  } finally { clearServiceAuthToken(); }
});

test('chat sessions are server-issued and can be explicitly cleared', () => {
  window.sessionStorage.clear();

  expect(getClientSessionId()).toBeNull();
  expect(window.sessionStorage.length).toBe(0);

  setClientSessionId('server-session');
  expect(getClientSessionId()).toBe('server-session');

  clearClientSessionId();
  expect(getClientSessionId()).toBeNull();
});

test('conversation bookmarks cannot cross deployment scopes', () => {
  setClientSessionId('private-conversation');
  sessionStorage.setItem('depo.sessionScope.v1', 'different-deployment');
  expect(getClientSessionId()).toBeNull();
});


test('credential changes cancel pending requests and reject late session adoption', async () => {
  clearServiceAuthToken();
  clearClientSessionId();
  const request = apiClient.interceptors.request.handlers[0].fulfilled({url:'http://legacy/chat',method:'get',headers:{}});
  window.dispatchEvent(new Event('depo:credentials-changed'));
  expect(request.signal.aborted).toBe(true);
  await expect(apiClient.interceptors.response.handlers[0].fulfilled({config:request,headers:{'x-session-id':'old-session'},data:{}})).rejects.toThrow(/previous credentials/);
  expect(getClientSessionId()).toBeNull();
});
