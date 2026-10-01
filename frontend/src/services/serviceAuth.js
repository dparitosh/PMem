// Runtime-only credential used by standalone services in token mode.
// It is deliberately never persisted or read from Vite build variables.
import { config } from '../config';
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
  gatewaySubscriptionKey = '';
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('depo:credentials-cleared'));
}

export function getServiceAuthToken() {
  return serviceToken;
}

export function serviceAuthHeaders(endpoint = '') {
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
    ...(serviceToken ? { Authorization: `Bearer ${serviceToken}` } : {}),
    ...(subscriptionAllowed ? { 'Ocp-Apim-Subscription-Key': gatewaySubscriptionKey } : {}),
  };
}
