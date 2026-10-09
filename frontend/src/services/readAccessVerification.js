import { buildSemanticServiceUrl, config } from '../config';
import { getCredentialProfile, handleSessionRejection, serviceAuthHeaders } from './serviceAuth';

export async function verifyStoredAccess(options = {}) {
  const read = await verifyStoredReadAccess(options);
  const key = getCredentialProfile('ADMIN_API_KEY');
  if (!key) return { ...read, message: `${read.message} Admin maintenance is not connected.` };
  const services = Object.keys(config.semanticServiceUrls || {}).filter(service => config.semanticServiceUrls[service]);
  const checks = await Promise.all(services.map(async service => {
    try {
      const endpoint = buildSemanticServiceUrl(service, '/auth/admin-access');
      const headers = { ...serviceAuthHeaders(endpoint, 'get', options.subscription), 'X-API-Key': key };
      delete headers.Authorization;
      const response = await fetch(endpoint, { headers, signal: options.signal, credentials: 'omit', redirect: 'error' });
      const body = await response.json().catch(() => ({}));
      if (response.ok && body.status === 'authorized') return { authorized: true };
      const detail = typeof body.detail === 'string' ? body.detail : 'Maintenance access was not authorized';
      if (!options.signal?.aborted && getCredentialProfile('ADMIN_API_KEY') === key) handleSessionRejection(response.status, key, detail);
      return { rejected: [401, 403].includes(response.status), message: `${service}: HTTP ${response.status}; ${detail}` };
    } catch (error) {
      return { message: `${service}: ${error.name === 'AbortError' ? 'Verification timed out' : 'Service could not be reached'}` };
    }
  }));
  const failures = checks.filter(check => !check.authorized);
  const changed = getCredentialProfile('ADMIN_API_KEY') !== key;
  const maintenance = !services.length ? 'Admin maintenance is unverified: no service endpoints configured.'
    : changed ? 'Admin maintenance access changed or expired; reconnect or verify the current session.'
    : failures.length ? `Admin maintenance verification failed: ${failures.map(check => check.message).join('; ')}`
    : `Admin maintenance verified: ${services.join(', ')}.`;
  const status = read.status === 'reconnect_required' || failures.some(check => check.rejected) ? 'reconnect_required'
    : read.status !== 'verified' || failures.length || changed || !services.length ? 'unverified' : 'verified';
  return { status, message: `${read.message} ${maintenance}` };
}

export async function verifyStoredReadAccess({ signal, subscription } = {}) {
  const token = getCredentialProfile('GRAPH_READ_TOKEN');
  if (!token) return { status: 'reconnect_required', message: 'Read access is not connected or has expired. Reconnect registered services.' };
  const services = Object.keys(config.semanticServiceUrls || {}).filter(service => config.semanticServiceUrls[service]);
  if (!services.length) return { status: 'unverified', message: 'No service endpoints are configured.' };
  const checks = await Promise.all(services.map(async service => {
    try {
      const endpoint = buildSemanticServiceUrl(service, '/auth/access');
      const response = await fetch(endpoint, { headers: { ...serviceAuthHeaders(endpoint, 'get', subscription), Authorization: `Bearer ${token}` }, signal, credentials: 'omit', redirect: 'error' });
      const body = await response.json().catch(() => ({}));
      if (response.ok && body?.status === 'authorized') return { service, authorized: true };
      const detail = typeof body?.detail === 'string' ? body.detail : 'Read access was not authorized';
      if (!signal?.aborted && getCredentialProfile('GRAPH_READ_TOKEN') === token) handleSessionRejection(response.status, `Bearer ${token}`, detail);
      return { service, rejected: [401, 403].includes(response.status), message: `${service}: HTTP ${response.status}; ${detail}` };
    } catch (error) {
      return { service, message: `${service}: ${error.name === 'AbortError' ? 'Verification timed out' : 'Service could not be reached'}` };
    }
  }));
  const failures = checks.filter(check => !check.authorized);
  const current = getCredentialProfile('GRAPH_READ_TOKEN');
  if (current !== token) return { status: current ? 'unverified' : 'reconnect_required', message: [failures.map(check => check.message).join('; '), 'Access changed or expired during verification. Reconnect or verify the current session.'].filter(Boolean).join(' ') };
  return failures.length ? { status: failures.some(check => check.rejected) ? 'reconnect_required' : 'unverified', message: failures.map(check => check.message).join('; ') }
    : { status: 'verified', message: `Read access verified: ${services.join(', ')}.` };
}
