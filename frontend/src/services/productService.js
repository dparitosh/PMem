import { apiClient } from './apiClient';
import { buildSemanticServiceUrl } from '../config';
import { loadProductCollection } from './productCollection';

export const PRODUCT_REFRESH_MS = 15000;
export const PRODUCT_CHANGED_EVENT = 'depo:products-changed';
const paths = { catalog: '/api/v1/catalog/products', dataProducts: '/api/v1/data-products' };
export async function readProductCollection(service, signal) {
  if (!paths[service]) throw new Error('Unknown product service.');
  const controller = new AbortController();
  const abort = () => controller.abort();
  let timedOut = false;
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const deadline = setTimeout(() => { timedOut = true; abort(); }, 60000);
  try {
    return await loadProductCollection(params => apiClient.get(buildSemanticServiceUrl(service, paths[service]),
      { params, signal: controller.signal, timeout: 15000 }), controller.signal);
  } catch (error) {
    if (timedOut) throw new Error('Product collection retrieval exceeded one minute.');
    throw error;
  } finally { clearTimeout(deadline); signal?.removeEventListener('abort', abort); }
}
export function productChanged() { window.dispatchEvent(new Event(PRODUCT_CHANGED_EVENT)); }
