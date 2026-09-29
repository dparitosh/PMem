// Runtime-only credential used by standalone services in token mode.
// It is deliberately never persisted or read from Vite build variables.
let serviceToken = '';

export function setServiceAuthToken(value) {
  serviceToken = String(value || '').trim();
}

export function clearServiceAuthToken() {
  serviceToken = '';
}

export function getServiceAuthToken() {
  return serviceToken;
}

export function serviceAuthHeaders() {
  return serviceToken ? { Authorization: `Bearer ${serviceToken}` } : {};
}
