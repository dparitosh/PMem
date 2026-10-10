import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { clearServiceAuthToken, getBrowserSessionStatus, getCredentialProfile, renewBrowserSession, setBrowserSessionExpiry, setCredentialProfile, installBrowserSession } from './serviceAuth';

vi.mock('../config', () => ({
  config: { semanticServiceUrls: { ontology: 'http://vm:8011' } },
  buildSemanticServiceUrl: (_service, path) => `http://vm:8011${path}`,
}));

beforeEach(() => clearServiceAuthToken());
afterEach(() => { clearServiceAuthToken(); vi.unstubAllGlobals(); vi.useRealTimers(); });

function connect() {
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_test');
  setBrowserSessionExpiry('depo_session_test', new Date(Date.now() + 120000).toISOString(), new Date(Date.now() + 3600000).toISOString());
}

test('reconnect preserves conversation bookmarks and invalid responses preserve credentials', () => {
  connect();
  sessionStorage.setItem('depo.sessionId.v1', 'conversation-one');
  const cleared = vi.fn();
  window.addEventListener('depo:credentials-cleared', cleared);
  const body = { token: 'depo_session_new', profiles: ['GRAPH_READ_TOKEN'], expires_at: new Date(Date.now()+600000).toISOString() };
  expect(() => installBrowserSession({ ...body, profiles: [] })).toThrow();
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_test');
  installBrowserSession(body);
  expect(cleared).not.toHaveBeenCalled();
  expect(sessionStorage.getItem('depo.sessionId.v1')).toBe('conversation-one');
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_new');
  window.removeEventListener('depo:credentials-cleared', cleared);
});

test('activity retries renewal after a transient failure without waiting for expiry', async () => {
  vi.useFakeTimers();
  connect();
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ok: true, json: async () => ({ token: 'depo_session_test', expires_at: new Date(Date.now()+600000).toISOString(), absolute_expires_at: new Date(Date.now()+3600000).toISOString() }) }));
  await vi.advanceTimersByTimeAsync(90000);
  expect(fetch).toHaveBeenCalledTimes(1);
  window.dispatchEvent(new Event('pointerdown'));
  await vi.advanceTimersByTimeAsync(1);
  expect(fetch).toHaveBeenCalledTimes(2);
});

test('invalid renewal metadata preserves the existing expiry timer and session', () => {
  connect();
  const original = getBrowserSessionStatus();
  expect(() => setBrowserSessionExpiry('depo_session_test', new Date(Date.now()+600000).toISOString(), 'invalid')).toThrow();
  expect(getBrowserSessionStatus()).toEqual(original);
});

test('renewal is single flight and persists the extended delegation', async () => {
  connect();
  const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ token: 'depo_session_test', expires_at: new Date(Date.now() + 600000).toISOString(), absolute_expires_at: new Date(Date.now() + 3600000).toISOString() }) }));
  vi.stubGlobal('fetch', fetch);
  await Promise.all([renewBrowserSession(), renewBrowserSession()]);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe('http://vm:8011/auth/browser-session/renew');
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer depo_session_test');
  expect(Date.parse(getBrowserSessionStatus().expiresAt)).toBeGreaterThan(Date.now() + 500000);
  expect(JSON.parse(sessionStorage.getItem('depo.browserSession.v1')).absoluteDeadline).toBeGreaterThan(Date.now());
});

test('late renewal cannot restore a logged-out session', async () => {
  connect();
  let resolve;
  vi.stubGlobal('fetch', vi.fn(() => new Promise(done => { resolve = done; })));
  const pending = renewBrowserSession();
  clearServiceAuthToken();
  resolve({ ok: true, json: async () => ({ token: 'depo_session_test', expires_at: new Date(Date.now()+600000).toISOString() }) });
  await pending;
  expect(getBrowserSessionStatus()).toBeNull();
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('');
});

test('revoked delegation clears all delegated credentials', async () => {
  connect();
  setCredentialProfile('INGESTION_WRITE_TOKEN', 'depo_session_test');
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 403, json: async () => ({ detail: 'Browser session scope is unavailable or credentials changed' }) })));
  await expect(renewBrowserSession()).rejects.toThrow('403');
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('');
  expect(getCredentialProfile('INGESTION_WRITE_TOKEN')).toBe('');
});
