export function notifyOntologyChange(response) {
  if (typeof window === 'undefined' || String(response?.config?.method || '').toLowerCase() !== 'post') return;
  const url = String(response.config.url || '').split('?')[0];
  if (!/\/api\/v1\/(?:ontologies\/register|ontologies\/merges\/[^/]+\/apply(?:-automatic)?|ontology\/upload|engineering-workflows)$/.test(url)) return;
  const status = String(response.data?.status || '').toLowerCase();
  if (['converted', 'policy_blocked', 'quality_blocked', 'failed', 'error', 'held'].includes(status)) return;
  window.dispatchEvent(new Event('depo:ontologies-changed'));
}
