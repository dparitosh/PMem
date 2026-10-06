// Runtime-only credential used by standalone services in token mode.
// It is deliberately never persisted or read from Vite build variables.
import { config } from '../config';
import { operationForUrl } from './serviceContractRegistry';
const profileTokens = new Map();
export function setCredentialProfile(profile, value) {
  if (!/^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(profile)) throw new Error('Invalid credential profile');
  const token = String(value || '').trim();
  if (profile === 'GRAPH_READ_TOKEN') { serviceToken = token; return; }
  if (token) profileTokens.set(profile, token); else profileTokens.delete(profile);
}
export function getCredentialProfile(profile) { checkBrowserSessionExpiry(); return profile === 'GRAPH_READ_TOKEN' ? serviceToken : (profileTokens.get(profile) || ''); }

let serviceToken = '';
let gatewaySubscriptionKey = '';
let browserSession = null;
let expiryTimer = null;
export function handleSessionRejection(status, authorization, detail = '') {
  const value = String(authorization || '');
  const invalidSession = status === 401 || (status === 403 &&
    /browser session scope is unavailable or credentials changed|invalid or revoked|expired session/i.test(String(detail)));
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
}

export function setGatewaySubscriptionKey(value) {
  gatewaySubscriptionKey = String(value || '').trim();
}

export function getGatewaySubscriptionKey() {
  return gatewaySubscriptionKey;
}

export function setServiceAuthToken(value) {
  serviceToken = String(value || '').trim();
}

export function clearServiceAuthToken() {
  clearTimeout(expiryTimer); expiryTimer = null; browserSession = null;
  serviceToken = '';
  profileTokens.clear();
  gatewaySubscriptionKey = '';
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:credentials-cleared'));
}

export function getServiceAuthToken() {
  checkBrowserSessionExpiry();
  return serviceToken;
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
