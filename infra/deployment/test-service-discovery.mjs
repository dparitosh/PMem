import assert from 'node:assert/strict';
import fs from 'node:fs';
const read = name => fs.readFileSync(`frontend/src/services/${name}.js`, 'utf8');
const registry = await import(`data:text/javascript;base64,${Buffer.from(read('serviceContractRegistry')).toString('base64')}`);
const contract = { openapi: '3.0.3', servers: [{ url: 'https://untrusted.example' }], paths: {
  '/api/v1/things': { post: { security: [{ BearerKey: [] }], 'x-depo-authorization': { credential_profiles: ['INGESTION_WRITE_TOKEN'] } } },
  '/api/v1/things/{thing_id}': { get: { security: [{ BearerKey: [] }], 'x-depo-authorization': { credential_profiles: ['GRAPH_READ_TOKEN'] } } },
  '/api/v1/admin': { post: { security: [{ ApiKey: [] }], 'x-depo-authorization': { credential_profiles: ['ADMIN_API_KEY'] } } },
  '/api/v1/unknown': { post: { security: [{ BearerKey: [] }] } },
  '/api/v1/ambiguous': { post: { security: [{ BearerKey: [] }], 'x-depo-authorization': { credential_profiles: ['INGESTION_WRITE_TOKEN', 'DATA_JOB_EXECUTION_TOKEN'] } } },
} };
for (const root of ['http://10.0.2.16:8014', 'https://gateway.example/depo/ingestion']) {
  registry.clearServiceContracts();
  registry.registerServiceContract('ingestion', root, contract);
  assert.equal(registry.serviceForContractPath('/api/v1/things/a', 'get'), 'ingestion');
  assert.equal(registry.operationForUrl(`${root}/api/v1/things/a?q=1`).profiles[0], 'GRAPH_READ_TOKEN');
  assert.equal(registry.operationForUrl('https://untrusted.example/api/v1/things', 'post'), null);
  globalThis.__registry = registry;
  const authSource = read('serviceAuth').replace("import { config } from '../config';", "const config = { gatewayUrl: 'https://gateway.example/depo' };")
    .replace("import { operationForUrl } from './serviceContractRegistry';", 'const { operationForUrl } = globalThis.__registry;');
  const auth = await import(`data:text/javascript;base64,${Buffer.from(authSource + `\n//${root}`).toString('base64')}`);
  auth.setServiceAuthToken('read'); auth.setCredentialProfile('INGESTION_WRITE_TOKEN', 'write'); auth.setCredentialProfile('ADMIN_API_KEY', 'admin');
  assert.equal(auth.serviceAuthHeaders(`${root}/api/v1/things`, 'post').Authorization, 'Bearer write');
  assert.equal(auth.serviceAuthHeaders(`${root}/api/v1/things/a`, 'get').Authorization, 'Bearer read');
  assert.equal(auth.serviceAuthHeaders(`${root}/api/v1/admin`, 'post')['X-API-Key'], 'admin');
  assert.equal(auth.serviceAuthHeaders(`${root}/api/v1/unknown`, 'post').Authorization, undefined);
  assert.equal(auth.serviceAuthHeaders(`${root}/api/v1/ambiguous`, 'post').Authorization, undefined);
  auth.clearServiceAuthToken();
  assert.equal(auth.getCredentialProfile('INGESTION_WRITE_TOKEN'), '');
}
console.log('PASS: imported ownership, parameters, scoped profile selection, admin header, unresolved/ambiguous rejection and clearing.');

globalThis.__register = registry.registerServiceContract;
const discoverySource = read('serviceDiscovery')
  .replace("import { registerServiceContract, removeServiceContract } from './serviceContractRegistry';", 'const registerServiceContract = globalThis.__register; const removeServiceContract = globalThis.__registry.removeServiceContract;')
  .replace("import { serviceAuthHeaders } from './serviceAuth';", 'const serviceAuthHeaders = () => ({});');
const discovery = await import(`data:text/javascript;base64,${Buffer.from(discoverySource).toString('base64')}`);
const results = await discovery.discoverServices({ ingestion: 'http://app:8014', offline: 'http://app:8015' }, async (url, options) => {
  assert.equal(options.redirect, 'error');
  if (url.includes('8015')) throw new Error('Offline');
  return { ok: true, text: async () => JSON.stringify(contract) };
});
assert.equal(results[0].status, 'imported');
assert.equal(results[1].status, 'failed');
console.log('PASS: discovery partial failure isolation and redirect rejection.');

registry.registerServiceContract('inherited', 'http://app:8020', { openapi: '3.0.3', security: [{ BearerKey: [] }], paths: { '/inherited': { post: {} } } });
assert.equal(registry.operationForUrl('http://app:8020/inherited', 'post').secured, true);
registry.registerServiceContract('offline', 'http://app:8015', contract);
await discovery.discoverServices({ offline: 'http://app:8015' }, async () => { throw new Error('Offline'); });
assert.equal(registry.operationForUrl('http://app:8015/api/v1/things', 'post'), null);
console.log('PASS: inherited security and stale contract removal after failed refresh.');
