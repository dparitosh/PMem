// Contract metadata only. Configured roots own credentials; OpenAPI servers are ignored.
const contracts = new Map();
const contractRoots = new Map();
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
  contractRoots.set(service, base.replace(/\/$/, ''));
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
  const owners = [...contractRoots.entries()].filter(([, base]) => {
    const root = new URL(base);
    return target.origin === root.origin && target.pathname.startsWith(`${root.pathname.replace(/\/$/, '')}/`);
  }).sort((a, b) => new URL(b[1]).pathname.length - new URL(a[1]).pathname.length);
  if (!owners.length) return null;
  // The most specific root owns the request, even if its contract has no match.
  const [service, base] = owners[0];
  const path = target.pathname.slice(new URL(base).pathname.replace(/\/$/, '').length);
  return contracts.get(service)?.find(operation => operation.method === method.toLowerCase() && operation.pattern.test(path)) || null;
}
export function serviceContractSummary(service) {
  const operations = contracts.get(service) || [];
  return { service, operationCount: operations.length, profiles: [...new Set(operations.flatMap(operation => operation.profiles))] };
}
export function hasServiceContract(service, base) {
  return contracts.has(service) && contractRoots.get(service) === base.replace(/\/$/, '');
}

export function clearServiceContracts() { contracts.clear(); contractRoots.clear(); }

export function removeServiceContract(service) { contracts.delete(service); contractRoots.delete(service); }
