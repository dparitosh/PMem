import { registerServiceContract, removeServiceContract, hasServiceContract, serviceContractSummary } from './serviceContractRegistry';
import { serviceAuthHeaders } from './serviceAuth';
const MAX_CONTRACT_BYTES = 5 * 1024 * 1024;
export async function readContractText(response) {
  const declared = Number(response.headers?.get('content-length'));
  if (declared > MAX_CONTRACT_BYTES) {
    await response.body?.cancel();
    throw new Error('Contract exceeds size limit');
  }
  if (!response.body?.getReader) throw new Error('Streaming contract response is required');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const parts = [];
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_CONTRACT_BYTES) throw new Error('Contract exceeds size limit');
      parts.push(decoder.decode(value, { stream: true }));
    }
    parts.push(decoder.decode());
    return parts.join('');
  } catch (error) {
    try { await reader.cancel(); } catch { /* Preserve the original error. */ }
    throw error;
  } finally { reader.releaseLock(); }
}
export async function discoverServices(roots, request = fetch, proposedSubscriptionKey = null) {
  return Promise.all(Object.entries(roots).map(async ([service, base]) => {
    // Retain a known contract during a same-root refresh; never reuse it at a new root.
    const retained = hasServiceContract(service, base);
    if (!retained) removeServiceContract(service);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const url = `${base.replace(/\/$/, '')}/openapi.json`;
      const headers = serviceAuthHeaders(url);
      if (proposedSubscriptionKey !== null && Object.prototype.hasOwnProperty.call(serviceAuthHeaders(url, 'get', proposedSubscriptionKey), 'Ocp-Apim-Subscription-Key')) {
        headers['Ocp-Apim-Subscription-Key'] = proposedSubscriptionKey;
      } else if (proposedSubscriptionKey !== null) {
        delete headers['Ocp-Apim-Subscription-Key'];
      }
      const response = await request(url, { headers, signal: controller.signal, redirect: 'error', credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await readContractText(response);
      return { ...registerServiceContract(service, base, JSON.parse(text)), status: 'imported' };
    } catch (error) {
      const message = error.name === 'AbortError' ? 'Timed out' : error.message === 'Contract exceeds size limit' ? 'Contract exceeds size limit' : 'Check service connectivity, CORS and contract validity.';
      return { ...(retained ? serviceContractSummary(service) : { service }), status: 'failed', retainedContract: retained, message: `${message}${retained ? ' Previous contract retained.' : ''}` };
    } finally { clearTimeout(timer); }
  }));
}
