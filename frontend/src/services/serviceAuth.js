// Raw API keys are memory-only. Only bounded, revocable delegated sessions
// survive same-tab refresh; no credentials come from Vite build variables.
import { config, buildSemanticServiceUrl } from '../config';
import { operationForUrl } from './serviceContractRegistry';
const profileTokens = new Map();
let browserAccessExpired = false;
export function wasBrowserSessionExpired() { return browserAccessExpired; }
export function setCredentialProfile(profile, value) {
  if (!/^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(profile)) throw new Error('Invalid credential profile');
  const token = String(value || '').trim();
  const previous = profile === 'GRAPH_READ_TOKEN' ? serviceToken : (profileTokens.get(profile) || '');
  if (previous !== token) clearPendingPublications();
  if (profile === 'GRAPH_READ_TOKEN') {
    if (browserSession && token !== browserSession.token) expireBrowserSession(browserSession.token);
    serviceToken = token; if (token) browserAccessExpired = false; persistBrowserSession(); return;
  }
  if (token) profileTokens.set(profile, token); else profileTokens.delete(profile);
  persistBrowserSession();
}
export function getCredentialProfile(profile) { checkBrowserSessionExpiry(); return profile === 'GRAPH_READ_TOKEN' ? serviceToken : (profileTokens.get(profile) || ''); }

let serviceToken = '';
let gatewaySubscriptionKey = '';
let browserSession = null;
let expiryTimer = null;
let renewalTimer = null;
let renewalInFlight = null;
let lastActivity = Date.now();
let lastRenewalAttempt = 0;
if (typeof window !== 'undefined') {
  const activity = () => {
    lastActivity = Date.now();
    if (browserSession && browserSession.deadline - Date.now() < 60000 && Date.now() - lastRenewalAttempt >= 10000) {
      renewBrowserSession().catch(() => {});
    }
  };
  window.addEventListener('pointerdown', activity, { passive: true });
  window.addEventListener('keydown', activity, { passive: true });
}
const BROWSER_SESSION_STORAGE_KEY = 'depo.browserSession.v1';
function connectionScope() {
  return JSON.stringify([config.gatewayUrl || '', Object.entries(config.semanticServiceUrls || {}).sort(([a], [b]) => a.localeCompare(b))]);
}
export function publicationRecoveryScope() { return connectionScope(); }
function clearPendingPublications() {
  try {
    if (typeof window === 'undefined') return;
    const storage = window.sessionStorage;
    for (let index = storage.length - 1; index >= 0; index--) {
      const key = storage.key(index);
        // Workflow bookmarks contain no credentials and must survive token
        // refresh: the server may still be executing their authorized writes.
        if (key === 'depo:agent-recommendation') storage.removeItem(key);
    }
  } catch { /* Restricted storage must not prevent credential revocation. */ }
}
function removeStoredSession() {
  try { if (typeof window !== 'undefined') window.sessionStorage?.removeItem(BROWSER_SESSION_STORAGE_KEY); }
  catch { /* Restricted storage still permits memory-only access. */ }
}
function persistBrowserSession() {
  if (!browserSession || serviceToken !== browserSession.token) { removeStoredSession(); return; }
  const profiles = ['GRAPH_READ_TOKEN', ...[...profileTokens].filter(([profile, token]) => token === browserSession.token).map(([profile]) => profile)];
  try {
    if (typeof window !== 'undefined') window.sessionStorage?.setItem(BROWSER_SESSION_STORAGE_KEY,
      JSON.stringify({ ...browserSession, profiles, subscription: gatewaySubscriptionKey, scope: connectionScope() }));
  } catch { /* Raw keys are never used as a persistence fallback. */ }
}
function restoreBrowserSession() {
  try {
    const raw = typeof window !== 'undefined' ? window.sessionStorage?.getItem(BROWSER_SESSION_STORAGE_KEY) : null;
    if (!raw) return;
    if (raw.length > 16384) throw new Error('Invalid stored session');
    const saved = JSON.parse(raw);
    if (saved.scope !== connectionScope() || typeof saved.token !== 'string' || !saved.token.startsWith('depo_session_') || saved.token.length > 4096 ||
        !Number.isFinite(saved.deadline) || saved.deadline <= Date.now() || saved.deadline > Date.now() + 15 * 60 * 1000 || !Array.isArray(saved.profiles) || saved.profiles.length > 32 ||
        !saved.profiles.includes('GRAPH_READ_TOKEN') || saved.profiles.some(profile => typeof profile !== 'string' || !/^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(profile))) throw new Error('Invalid stored session');
    setBrowserSessionExpiry(saved.token, new Date(saved.deadline).toISOString(), saved.absoluteDeadline ? new Date(saved.absoluteDeadline).toISOString() : null);
    gatewaySubscriptionKey = typeof saved.subscription === 'string' && saved.subscription.length <= 4096 ? saved.subscription : '';
    serviceToken = saved.token;
    saved.profiles.filter(profile => profile !== 'GRAPH_READ_TOKEN').forEach(profile => profileTokens.set(profile, saved.token));
    persistBrowserSession();
  } catch { removeStoredSession(); }
}
export function handleSessionRejection(status, authorization, detail = '') {
  const value = String(authorization || '');
  const invalidSession = status === 401 || (status === 403 &&
    /browser session scope is unavailable or credentials changed|invalid or revoked|^revoked [A-Z_]+|expired session/i.test(String(detail)));
  if (invalidSession && value.startsWith('Bearer depo_session_')) expireBrowserSession(value.slice(7));
  else if (invalidSession && value.startsWith('depo_session_')) expireBrowserSession(value);
}
function checkBrowserSessionExpiry() {
  if (browserSession && Date.now() >= browserSession.deadline) expireBrowserSession(browserSession.token);
}

export function expireBrowserSession(token) {
  if (!browserSession || browserSession.token !== token) return;
  browserAccessExpired = true;
  clearPendingPublications();
  if (serviceToken === token) serviceToken = '';
  for (const [profile, value] of profileTokens) if (value === token) profileTokens.delete(profile);
  browserSession = null;
  removeStoredSession();
  clearTimeout(expiryTimer); expiryTimer = null;
  clearTimeout(renewalTimer); renewalTimer = null;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('depo:session-expired'));
    window.dispatchEvent(new Event('depo:credentials-changed'));
  }
}

function validateSessionExpiry(token, expiresAt, absoluteExpiresAt = null) {
  const deadline = Date.parse(expiresAt);
  if (!token?.startsWith('depo_session_') || !Number.isFinite(deadline) || deadline <= Date.now() || deadline > Date.now() + 15 * 60 * 1000) throw new Error('Central session expiry must be within the next fifteen minutes.');
  const absoluteDeadline = absoluteExpiresAt ? Date.parse(absoluteExpiresAt) : null;
  if (absoluteExpiresAt && (!Number.isFinite(absoluteDeadline) || absoluteDeadline < deadline)) throw new Error('Invalid absolute session expiry');
  return { token, deadline, absoluteDeadline };
}

export function installBrowserSession(body, subscription = '') {
  validateSessionExpiry(body.token, body.expires_at, body.absolute_expires_at);
  if (!Array.isArray(body.profiles) || body.profiles.length > 32 || !body.profiles.includes('GRAPH_READ_TOKEN') ||
      body.profiles.some(profile => !/^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(profile))) throw new Error('Invalid delegated scopes');
  setBrowserSessionExpiry(body.token, body.expires_at, body.absolute_expires_at);
  serviceToken = body.token;
  profileTokens.clear();
  body.profiles.filter(profile => profile !== 'GRAPH_READ_TOKEN').forEach(profile => profileTokens.set(profile, body.token));
  gatewaySubscriptionKey = String(subscription || '').trim();
  browserAccessExpired = false;
  lastActivity = Date.now();
  persistBrowserSession();
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:session-replaced'));
}

export function setBrowserSessionExpiry(token, expiresAt, absoluteExpiresAt = null) {
  const { deadline, absoluteDeadline } = validateSessionExpiry(token, expiresAt, absoluteExpiresAt);
  clearTimeout(expiryTimer);
  browserSession = { token, deadline, absoluteDeadline };
  expiryTimer = setTimeout(() => expireBrowserSession(token), Math.min(deadline - Date.now(), 2147483647));
  clearTimeout(renewalTimer);
  if (absoluteDeadline && absoluteDeadline > deadline) {
    renewalTimer = setTimeout(() => {
      // Passive/background tabs do not keep an authentication session alive.
      if (Date.now() - lastActivity < 10 * 60 * 1000) renewBrowserSession().catch(() => {});
    }, Math.max(1000, (deadline - Date.now()) - Math.min(60000, (deadline - Date.now()) / 3)));
  }
  persistBrowserSession();
}

export async function renewBrowserSession() {
  if (renewalInFlight) return renewalInFlight;
  checkBrowserSessionExpiry();
  const current = browserSession;
  if (!current?.absoluteDeadline || Date.now() >= current.absoluteDeadline) return null;
  lastRenewalAttempt = Date.now();
  renewalInFlight = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const url = buildSemanticServiceUrl('ontology', '/auth/browser-session/renew');
      const response = await fetch(url, { method: 'POST', credentials: 'omit', redirect: 'error',
        headers: { ...serviceAuthHeaders(url, 'post'), Authorization: `Bearer ${current.token}` }, signal: controller.signal });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        handleSessionRejection(response.status, `Bearer ${current.token}`, body.detail);
        throw new Error(`Session renewal failed (${response.status})`);
      }
      // A concurrent logout or reconnect must never be undone by a late reply.
      if (browserSession?.token !== current.token) return null;
      if (body.token !== current.token) throw new Error('Invalid renewed session');
      setBrowserSessionExpiry(body.token, body.expires_at, body.absolute_expires_at);
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:session-renewed'));
      return getBrowserSessionStatus();
    } catch (error) {
      // Retry transport/server failures within the existing session lifetime.
      if (browserSession?.token === current.token && current.deadline - Date.now() > 11000) {
        clearTimeout(renewalTimer);
        renewalTimer = setTimeout(() => {
          if (Date.now() - lastActivity < 10 * 60 * 1000) renewBrowserSession().catch(() => {});
        }, 10000);
      }
      throw error;
    } finally { clearTimeout(timer); }
  })();
  try { return await renewalInFlight; } finally { renewalInFlight = null; }
}

export function setGatewaySubscriptionKey(value) {
  gatewaySubscriptionKey = String(value || '').trim();
  persistBrowserSession();
}

export function getGatewaySubscriptionKey() {
  return gatewaySubscriptionKey;
}

export function setServiceAuthToken(value) {
  setCredentialProfile('GRAPH_READ_TOKEN', value);
}

export function clearServiceAuthToken() {
  browserAccessExpired = false;
  clearPendingPublications();
  clearTimeout(expiryTimer); expiryTimer = null; browserSession = null;
  clearTimeout(renewalTimer); renewalTimer = null;
  removeStoredSession();
  serviceToken = '';
  profileTokens.clear();
  gatewaySubscriptionKey = '';
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:credentials-cleared'));
}

restoreBrowserSession();

export function getServiceAuthToken() {
  checkBrowserSessionExpiry();
  return serviceToken;
}

export function getBrowserSessionStatus() {
  checkBrowserSessionExpiry();
  if (!browserSession || serviceToken !== browserSession.token) return null;
  const profiles = ['GRAPH_READ_TOKEN', ...[...profileTokens].filter(([profile, token]) => token === browserSession.token).map(([profile]) => profile)];
  return { expiresAt: new Date(browserSession.deadline).toISOString(), profiles };
}

// These reads have the same server-owned authorization contract even before
// OpenAPI discovery finishes. Never let contract import remove their read key.
function isServiceRead(endpoint, method) {
  if (String(method).toLowerCase() !== 'get') return false;
  try {
    const target = new URL(endpoint);
    return Object.entries(config.semanticServiceUrls || {}).some(([service, base]) => {
      if (!base) return false;
      const root = new URL(base);
      if (target.origin !== root.origin || target.username || target.password) return false;
      const path = target.pathname.slice(root.pathname.replace(/\/$/, '').length);
      if (!target.pathname.startsWith(`${root.pathname.replace(/\/$/, '')}/`)) return false;
      return ({ graph: /^\/api\/v1\/graph\/metrics\/?$/, agentic: /^\/api\/v1\/observability\/summary\/?$/, catalog: /^\/api\/v1\/catalog\/products\/?$/, dataProducts: /^\/api\/v1\/data-products\/?$/ })[service]?.test(path) || false;
    });
  } catch { return false; }
}

export function requireServiceReadAccess(request) {
  if (!isServiceRead(request.url, request.method || 'get')) return;
  const authorization = request.headers?.get?.('Authorization') || request.headers?.Authorization || request.headers?.authorization;
  const apiKey = request.headers?.get?.('X-API-Key') || request.headers?.['X-API-Key'];
  if (authorization || apiKey) return;
  const error = new Error('Service read access is not connected or has expired. Open Admin → Connect registered services. PostgreSQL keys do not need to be re-entered individually.');
  error.code = 'DEPO_READ_ACCESS_REQUIRED';
  error.config = request;
  throw error;
}

export function serviceAuthHeaders(endpoint = '', method = 'get', subscription = gatewaySubscriptionKey) {
  checkBrowserSessionExpiry();
  if (!isConfiguredServiceEndpoint(endpoint)) return {};
  const operation = operationForUrl(endpoint, method);
  const profile = isServiceRead(endpoint, method) ? 'GRAPH_READ_TOKEN' : operation?.profiles.length === 1 ? operation.profiles[0] : null;
  const token = profile ? getCredentialProfile(profile) : (operation && (operation.profiles.length || operation.secured) ? '' : serviceToken);
  let subscriptionAllowed = false;
  if (subscription && config.gatewayUrl) {
    try {
      const gateway = new URL(config.gatewayUrl);
      const target = new URL(endpoint || config.gatewayUrl);
      const decodedPath = decodeURIComponent(target.pathname);
      const safePath = !decodedPath.includes('\\') && !decodedPath.split('/').some(part => part === '.' || part === '..');
      subscriptionAllowed = !target.username && !target.password && safePath && target.origin === gateway.origin &&
        (decodedPath === gateway.pathname || decodedPath.startsWith(`${gateway.pathname.replace(/\/$/, '')}/`));
    } catch { /* Invalid URLs never receive subscription credentials. */ }
  }
  return {
    ...(token ? (profile === 'ADMIN_API_KEY' ? { 'X-API-Key': token } : { Authorization: `Bearer ${token}` }) : {}),
    ...(subscriptionAllowed ? { 'Ocp-Apim-Subscription-Key': subscription } : {}),
  };
}

function isConfiguredServiceEndpoint(endpoint) {
  try {
    const target = new URL(endpoint);
    const decoded = decodeURIComponent(target.pathname);
    if (target.username || target.password || decoded.includes('\\') || decoded.split('/').some(part => part === '.' || part === '..')) return false;
    return Object.values(config.semanticServiceUrls || {}).some(base => {
      if (!base) return false;
      const root = new URL(base);
      const path = root.pathname.replace(/\/$/, '');
      return target.origin === root.origin && (decoded === path || decoded.startsWith(`${path}/`));
    });
  } catch { return false; }
}
