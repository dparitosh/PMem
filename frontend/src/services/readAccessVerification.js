import { buildSemanticServiceUrl, config } from '../config';
import { abortableDelay } from './requestPolicy';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { getCredentialProfile, handleSessionRejection, serviceAuthHeaders } from './serviceAuth';

// The server control-request budget is 15 seconds. Allow its response to finish,
// retry only a transient read once, and keep successful services independent.
export const ACCESS_ATTEMPT_MS = 16000;
export const ACCESS_VERIFICATION_MS = 40000;
async function accessResponse(endpoint, headers, signal, stillCurrent) {
  for (let attempt = 0; attempt < 2; attempt++) {
    if (signal?.aborted || !stillCurrent()) throw new DOMException('Access changed', 'AbortError');
    const controller = new AbortController();
    let timer, abort;
    const cancelled = new Promise((_, reject) => {
      abort = () => { controller.abort(); reject(new DOMException('Aborted', 'AbortError')); };
      signal?.addEventListener('abort', abort, { once: true });
      timer = setTimeout(() => { controller.abort(); reject(new DOMException('Verification timed out', 'TimeoutError')); }, ACCESS_ATTEMPT_MS);
    });
    try {
      const result = await Promise.race([cancelled, (async () => {
        const response = await fetch(endpoint, { headers, signal: controller.signal, credentials: 'omit', redirect: 'error' });
        const body = await response.json().catch(() => ({}));
        return { response, body };
      })()]);
      if (!attempt && [502, 503, 504].includes(result.response.status) && !signal?.aborted && stillCurrent()) {
        // Retry below after the attempt's timer/listener have been released.
      } else return result;
    } catch (error) {
      if (attempt || signal?.aborted || !stillCurrent() || !['TimeoutError', 'TypeError'].includes(error.name)) throw error;
    } finally {
      clearTimeout(timer); signal?.removeEventListener('abort', abort);
    }
    await abortableDelay(300, signal);
  }
}

export async function verifyStoredAccess(options = {}) {
  const readPromise = verifyStoredReadAccess(options);
  const key = getCredentialProfile('ADMIN_API_KEY');
  // Optional destructive-maintenance access is explained in Admin, not global read status.
  if (!key) return readPromise;
  const services = Object.keys(config.semanticServiceUrls || {}).filter(service => config.semanticServiceUrls[service]);
  const checks = await Promise.all(services.map(async service => {
    try {
      const endpoint = buildSemanticServiceUrl(service, '/auth/admin-access');
      const headers = { ...serviceAuthHeaders(endpoint, 'get', options.subscription), 'X-API-Key': key };
      delete headers.Authorization;
      const { response, body } = await accessResponse(endpoint, headers, options.signal, () => getCredentialProfile('ADMIN_API_KEY') === key);
      if (response.ok && body.status === 'authorized') return { authorized: true };
      const detail = typeof body.detail === 'string' ? body.detail : 'Maintenance access was not authorized';
      if (!options.signal?.aborted && getCredentialProfile('ADMIN_API_KEY') === key) handleSessionRejection(response.status, key, detail);
      return { rejected: [401, 403].includes(response.status), message: `${service}: HTTP ${response.status}; ${apiErrorMessage({ response: { data: body, headers: response.headers, status: response.status } }, detail)}` };
    } catch (error) {
      return { message: `${service}: ${['AbortError', 'TimeoutError'].includes(error.name) ? 'Verification timed out' : 'Service could not be reached'}` };
    }
  }));
  const read = await readPromise;
  const failures = checks.filter(check => !check.authorized);
  const changed = getCredentialProfile('ADMIN_API_KEY') !== key;
  const maintenance = !services.length ? 'Admin maintenance is unverified: no service endpoints configured.'
    : changed ? 'Admin maintenance access changed or expired; reconnect or verify the current session.'
    : failures.length ? `Admin maintenance verification failed: ${failures.map(check => check.message).join('; ')}`
    : `Admin maintenance verified: ${services.join(', ')}.`;
  const status = read.status === 'reconnect_required' || failures.some(check => check.rejected) ? 'reconnect_required'
    : read.status !== 'verified' || failures.length || changed || !services.length ? 'unverified' : 'verified';
  const summary = status === 'verified' ? read.message : `${read.message} ${maintenance}`;
  return { status, message: summary, detail: [read.detail || read.message, maintenance].join(' ') };
}

export async function verifyStoredReadAccess({ signal, subscription } = {}) {
  const token = getCredentialProfile('GRAPH_READ_TOKEN');
  if (!token) return { status: 'reconnect_required', message: 'Read access is not connected or has expired. Reconnect registered services.' };
  const services = Object.keys(config.semanticServiceUrls || {}).filter(service => config.semanticServiceUrls[service]);
  if (!services.length) return { status: 'unverified', message: 'No service endpoints are configured.' };
  const checks = await Promise.all(services.map(async service => {
    try {
      const endpoint = buildSemanticServiceUrl(service, '/auth/access');
      const { response, body } = await accessResponse(endpoint, { ...serviceAuthHeaders(endpoint, 'get', subscription), Authorization: `Bearer ${token}` }, signal, () => getCredentialProfile('GRAPH_READ_TOKEN') === token);
      if (response.ok && body?.status === 'authorized') return { service, authorized: true };
      const detail = typeof body?.detail === 'string' ? body.detail : 'Read access was not authorized';
      if (!signal?.aborted && getCredentialProfile('GRAPH_READ_TOKEN') === token) handleSessionRejection(response.status, `Bearer ${token}`, detail);
      return { service, rejected: [401, 403].includes(response.status), message: `${service}: HTTP ${response.status}; ${apiErrorMessage({ response: { data: body, headers: response.headers, status: response.status } }, detail)}` };
    } catch (error) {
      return { service, message: `${service}: ${['AbortError', 'TimeoutError'].includes(error.name) ? 'Verification timed out' : 'Service could not be reached'}` };
    }
  }));
  const failures = checks.filter(check => !check.authorized);
  const current = getCredentialProfile('GRAPH_READ_TOKEN');
  if (current !== token) return { status: current ? 'unverified' : 'reconnect_required', message: [failures.map(check => check.message).join('; '), 'Access changed or expired during verification. Reconnect or verify the current session.'].filter(Boolean).join(' ') };
  return failures.length ? { status: failures.some(check => check.rejected) ? 'reconnect_required' : 'unverified', message: `Read access verified for ${services.length - failures.length} of ${services.length} services. ${failures.map(check => check.message).join('; ')}` }
    : { status: 'verified', message: `Connected to ${services.length} ${services.length === 1 ? 'service' : 'services'}.`, detail: `Read access verified: ${services.join(', ')}.` };
}
