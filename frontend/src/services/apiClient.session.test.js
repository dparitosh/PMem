import { clearClientSessionId, getClientSessionId, setClientSessionId } from './apiClient';
import apiClient from './apiClient';
import { vi } from 'vitest';
vi.unmock('axios');
import { AxiosHeaders } from 'axios';
import { buildUrl } from '../config';
import { clearServiceAuthToken, setCredentialProfile } from './serviceAuth';

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
