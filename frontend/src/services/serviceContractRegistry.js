// Contract metadata only. Configured roots own credentials; OpenAPI servers are ignored.
const contracts = new Map();
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options']);
export function registerServiceContract(service, base, document) {
  if (!/^3\.[01]\./.test(document?.openapi || '') || !document.paths || typeof document.paths !== 'object') throw new Error('Invalid OpenAPI contract');
  const root = new URL(base);
  if (!['http:', 'https:'].includes(root.protocol) || root.username || root.password || root.search || root.hash) throw new Error('Invalid service root');
  const operations = [];
  for (const [path, entries] of Object.entries(document.paths)) {
    if (!path.startsWith('/') || path.includes('..') || path.includes('\\') || path.includes('?') || path.includes('#')) continue;
    const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`^${escaped.replace(/\\\{[^}]+\\\}/g, '[^/]+')}/?$`);
    for (const [method, operation] of Object.entries(entries)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object') continue;
      const metadata = operation['x-depo-authorization'];
      const profiles = Array.isArray(metadata?.credential_profiles) ? metadata.credential_profiles.filter(name => /^(?:[A-Z][A-Z0-9_]*_TOKEN|ADMIN_API_KEY)$/.test(name)) : [];
      operations.push({ service, base: base.replace(/\/$/, ''), path, method, pattern, profiles, secured: Boolean((operation.security ?? document.security)?.some(requirement => Object.keys(requirement).length)) });
    }
  }
  operations.sort((a, b) => (a.path.includes('{') - b.path.includes('{')) || b.path.length - a.path.length);
  contracts.set(service, operations);
  return { service, operationCount: operations.length, profiles: [...new Set(operations.flatMap(operation => operation.profiles))] };
}
export function serviceForContractPath(path, method = null) {
  const owners = [...contracts.values()].filter(operations => operations.some(op => (!method || op.method === method.toLowerCase()) && op.pattern.test(path)));
  return owners.length === 1 ? owners[0][0]?.service : null;
}
export function operationForUrl(endpoint, method = 'get') {
  let target;
  try { target = new URL(endpoint); } catch { return null; }
  if (target.username || target.password) return null;
  for (const operations of contracts.values()) {
    for (const operation of operations) {
      const root = new URL(operation.base);
      if (target.origin !== root.origin || !target.pathname.startsWith(`${root.pathname.replace(/\/$/, '')}/`)) continue;
      const path = target.pathname.slice(root.pathname.replace(/\/$/, '').length);
      if (operation.method === method.toLowerCase() && operation.pattern.test(path)) return operation;
    }
  }
  return null;
}
export function clearServiceContracts() { contracts.clear(); }

export function removeServiceContract(service) { contracts.delete(service); }
