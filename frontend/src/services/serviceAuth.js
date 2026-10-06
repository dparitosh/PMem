// Raw API keys are memory-only. Only bounded, revocable delegated sessions
// survive same-tab refresh; no credentials come from Vite build variables.
import { config } from '../config';
import { operationForUrl } from './serviceContractRegistry';
const profileTokens = new Map();
export function setCredentialProfile(profile, value) {
  if (!/^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(profile)) throw new Error('Invalid credential profile');
  const token = String(value || '').trim();
  if (profile === 'GRAPH_READ_TOKEN') { serviceToken = token; persistBrowserSession(); return; }
  if (token) profileTokens.set(profile, token); else profileTokens.delete(profile);
  persistBrowserSession();
}
export function getCredentialProfile(profile) { checkBrowserSessionExpiry(); return profile === 'GRAPH_READ_TOKEN' ? serviceToken : (profileTokens.get(profile) || ''); }

let serviceToken = '';
let gatewaySubscriptionKey = '';
let browserSession = null;
let expiryTimer = null;
const BROWSER_SESSION_STORAGE_KEY = 'depo.browserSession.v1';
function connectionScope() {
  return JSON.stringify([config.gatewayUrl || '', Object.entries(config.semanticServiceUrls || {}).sort(([a], [b]) => a.localeCompare(b))]);
}
function removeStoredSession() {
  try { if (typeof window !== 'undefined') window.sessionStorage?.removeItem(BROWSER_SESSION_STORAGE_KEY); }
  catch { /* Restricted storage still permits memory-only access. */ }
}
function persistBrowserSession() {
  if (!browserSession || serviceToken !== browserSession.token) { removeStoredSession(); return; }
  const profiles = ['GRAPH_READ_TOKEN', ...[...profileTokens].filter(([profile, token]) => profile !== 'ADMIN_API_KEY' && token === browserSession.token).map(([profile]) => profile)];
  try {
    if (typeof window !== 'undefined') window.sessionStorage?.setItem(BROWSER_SESSION_STORAGE_KEY,
      JSON.stringify({ ...browserSession, profiles, scope: connectionScope() }));
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
        !saved.profiles.includes('GRAPH_READ_TOKEN') || saved.profiles.some(profile => typeof profile !== 'string' || !/^[A-Z][A-Z0-9_]*_TOKEN$/.test(profile))) throw new Error('Invalid stored session');
    serviceToken = saved.token;
    saved.profiles.filter(profile => profile !== 'GRAPH_READ_TOKEN').forEach(profile => profileTokens.set(profile, saved.token));
    setBrowserSessionExpiry(saved.token, new Date(saved.deadline).toISOString());
  } catch { removeStoredSession(); }
}
export function handleSessionRejection(status, authorization, detail = '') {
  const value = String(authorization || '');
  const invalidSession = status === 401 || (status === 403 &&
    /browser session scope is unavailable or credentials changed|invalid or revoked|^revoked [A-Z_]+|expired session/i.test(String(detail)));
  if (invalidSession && value.startsWith('Bearer depo_session_')) expireBrowserSession(value.slice(7));
}
function checkBrowserSessionExpiry() {
  if (browserSession && Date.now() >= browserSession.deadline) expireBrowserSession(browserSession.token);
}

export function expireBrowserSession(token) {
  if (!browserSession || browserSession.token !== token) return;
  if (serviceToken === token) serviceToken = '';
  for (const [profile, value] of profileTokens) if (value === token) profileTokens.delete(profile);
  browserSession = null;
  removeStoredSession();
  clearTimeout(expiryTimer); expiryTimer = null;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('depo:session-expired'));
    window.dispatchEvent(new Event('depo:credentials-changed'));
  }
}

export function setBrowserSessionExpiry(token, expiresAt) {
  const deadline = Date.parse(expiresAt);
  if (!token?.startsWith('depo_session_') || !Number.isFinite(deadline) || deadline <= Date.now()) throw new Error('Central session expiry is invalid or already elapsed.');
  clearTimeout(expiryTimer);
  browserSession = { token, deadline };
  expiryTimer = setTimeout(() => expireBrowserSession(token), Math.min(deadline - Date.now(), 2147483647));
  persistBrowserSession();
}

export function setGatewaySubscriptionKey(value) {
  gatewaySubscriptionKey = String(value || '').trim();
}

export function getGatewaySubscriptionKey() {
  return gatewaySubscriptionKey;
}

export function setServiceAuthToken(value) {
  serviceToken = String(value || '').trim();
  persistBrowserSession();
}

export function clearServiceAuthToken() {
  clearTimeout(expiryTimer); expiryTimer = null; browserSession = null;
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
  const profiles = ['GRAPH_READ_TOKEN', ...[...profileTokens].filter(([profile, token]) => profile !== 'ADMIN_API_KEY' && token === browserSession.token).map(([profile]) => profile)];
  return { expiresAt: new Date(browserSession.deadline).toISOString(), profiles };
}

export function serviceAuthHeaders(endpoint = '', method = 'get', subscription = gatewaySubscriptionKey) {
  checkBrowserSessionExpiry();
  const operation = operationForUrl(endpoint, method);
  const profile = operation?.profiles.length === 1 ? operation.profiles[0] : null;
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
