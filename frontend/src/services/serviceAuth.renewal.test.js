import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { clearServiceAuthToken, getBrowserSessionStatus, getCredentialProfile, renewBrowserSession, setBrowserSessionExpiry, setCredentialProfile, installBrowserSession, handleSessionRejection, wasBrowserSessionExpired } from './serviceAuth';

vi.mock('../config', () => ({
  config: { semanticServiceUrls: { ontology: 'http://vm:8011' } },
  buildSemanticServiceUrl: (_service, path) => `http://vm:8011${path}`,
}));

beforeEach(() => clearServiceAuthToken());
afterEach(() => { clearServiceAuthToken(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

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

test('automatic renewal retries a transient failure without user activity', async () => {
  vi.useFakeTimers();
  connect();
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ok: true, json: async () => ({ token: 'depo_session_test', expires_at: new Date(Date.now()+600000).toISOString(), absolute_expires_at: new Date(Date.now()+3600000).toISOString() }) }));
  await vi.advanceTimersByTimeAsync(90000);
  expect(fetch).toHaveBeenCalledTimes(2);
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

test.each(['scroll', 'wheel', 'input', 'keydown'])('nested %s activity keeps the session renewable across pages', async eventName => {
  vi.useFakeTimers();
  installBrowserSession({token:'depo_session_test', profiles:['GRAPH_READ_TOKEN'],
    expires_at:new Date(Date.now()+900000).toISOString(), absolute_expires_at:new Date(Date.now()+3600000).toISOString()});
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:true, json:async () => ({token:'depo_session_test',
    expires_at:new Date(Date.now()+900000).toISOString(), absolute_expires_at:new Date(Date.now()+3600000).toISOString()})})));
  await vi.advanceTimersByTimeAsync(780000);
  const panel = document.createElement('div');
  document.body.appendChild(panel);
  panel.addEventListener(eventName, event => event.stopPropagation());
  panel.dispatchEvent(new Event(eventName, {bubbles:false}));
  await vi.advanceTimersByTimeAsync(60000);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(getCredentialProfile('GRAPH_READ_TOKEN')).toBe('depo_session_test');
  panel.remove();
});

test('a hidden tab does not renew from timers or background activity', async () => {
  vi.useFakeTimers();
  connect();
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
  vi.stubGlobal('fetch', vi.fn());
  window.dispatchEvent(new Event('scroll'));
  await vi.advanceTimersByTimeAsync(120001);
  expect(fetch).not.toHaveBeenCalled();
  expect(getBrowserSessionStatus()).toBeNull();
});

test.each(['focus', 'online', 'visibilitychange'])('returning via %s renews before expiry without an admin key', async eventName => {
  vi.useFakeTimers();
  installBrowserSession({token:'depo_session_test', profiles:['GRAPH_READ_TOKEN'],
    expires_at:new Date(Date.now()+45000).toISOString(), absolute_expires_at:new Date(Date.now()+3600000).toISOString()});
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:true, json:async () => ({token:'depo_session_test',
    expires_at:new Date(Date.now()+900000).toISOString(), absolute_expires_at:new Date(Date.now()+3600000).toISOString()})})));
  (eventName === 'visibilitychange' ? document : window).dispatchEvent(new Event(eventName));
  await vi.advanceTimersByTimeAsync(1);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer depo_session_test');
  expect(getCredentialProfile('ADMIN_API_KEY')).toBe('');
  expect(Date.parse(getBrowserSessionStatus().expiresAt)).toBeGreaterThan(Date.now()+800000);
});

test('returning after expiry prompts reconnection without trying to revive the session', async () => {
  vi.useFakeTimers();
  connect();
  vi.stubGlobal('fetch', vi.fn());
  vi.setSystemTime(Date.now()+120001); // Simulate a sleeping tab with suspended timers.
  const expired = vi.fn();
  window.addEventListener('depo:session-expired', expired);
  try {
    window.dispatchEvent(new Event('focus'));
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getBrowserSessionStatus()).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  } finally { window.removeEventListener('depo:session-expired', expired); }
});

test('403 session expired wording invalidates the delegation', () => {
  connect();
  handleSessionRejection(403, 'Bearer depo_session_test', 'Browser service session expired; reconnect in Admin');
  expect(getBrowserSessionStatus()).toBeNull();
  expect(wasBrowserSessionExpired()).toBe(true);
});

test('generic credential rejection clears only the presented delegated session for local recovery', () => {
  connect();
  handleSessionRejection(403, 'Bearer depo_session_test', 'Required API key is missing or invalid');
  expect(getBrowserSessionStatus()).toBeNull();
  expect(wasBrowserSessionExpired()).toBe(true);
});
