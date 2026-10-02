import { registerServiceContract, removeServiceContract } from './serviceContractRegistry';
import { serviceAuthHeaders } from './serviceAuth';
export async function discoverServices(roots, request = fetch) {
  return Promise.all(Object.entries(roots).map(async ([service, base]) => {
    removeServiceContract(service);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const url = `${base.replace(/\/$/, '')}/openapi.json`;
      const response = await request(url, { headers: serviceAuthHeaders(url), signal: controller.signal, redirect: 'error', credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text();
      if (text.length > 5 * 1024 * 1024) throw new Error('Contract exceeds size limit');
      return { ...registerServiceContract(service, base, JSON.parse(text)), status: 'imported' };
    } catch (error) { return { service, status: 'failed', message: error.name === 'AbortError' ? 'Timed out' : 'Check service connectivity, CORS and gateway access.' }; }
    finally { clearTimeout(timer); }
  }));
}
