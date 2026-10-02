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
export function getCredentialProfile(profile) { return profile === 'GRAPH_READ_TOKEN' ? serviceToken : (profileTokens.get(profile) || ''); }

let serviceToken = '';
let gatewaySubscriptionKey = '';

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
  serviceToken = '';
  profileTokens.clear();
  gatewaySubscriptionKey = '';
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:credentials-cleared'));
}

export function getServiceAuthToken() {
  return serviceToken;
}

export function serviceAuthHeaders(endpoint = '', method = 'get') {
  const operation = operationForUrl(endpoint, method);
  const profile = operation?.profiles.length === 1 ? operation.profiles[0] : null;
  const token = profile ? getCredentialProfile(profile) : (operation && (operation.profiles.length || operation.secured) ? '' : serviceToken);
  let subscriptionAllowed = false;
  if (gatewaySubscriptionKey && config.gatewayUrl) {
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
    ...(subscriptionAllowed ? { 'Ocp-Apim-Subscription-Key': gatewaySubscriptionKey } : {}),
  };
}
