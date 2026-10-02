// Dependency-free routing contract checks; execute with Node.js.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const source = fs.readFileSync(new URL('../../frontend/src/config.js', import.meta.url), 'utf8')
  .replace("import { serviceForContractPath } from './services/serviceContractRegistry';", 'const serviceForContractPath = () => null;')
  .replaceAll('import.meta.env', 'globalThis.__DEPO_TEST_VITE_ENV__');
const names = ['QIF', 'ONTOLOGY', 'AGENTIC', 'GRAPH', 'INGESTION', 'OSLC', 'CATALOG', 'DATA_PRODUCT', 'CEIM', 'DATA_PIPELINE'];
const paths = ['qif', 'ontology', 'agentic', 'graph', 'ingestion', 'oslc', 'catalog', 'data-products', 'ceim', 'data-pipeline'];
const ids = ['qif', 'ontology', 'agentic', 'graph', 'ingestion', 'oslc', 'catalog', 'dataProducts', 'ceim', 'dataPipeline'];
for (const mode of ['local', 'gateway']) {
  const runtime = { VITE_BACKEND_URL: '', VITE_API_GATEWAY_URL: mode === 'gateway' ? 'https://customer.example/depo' : '' };
  names.forEach((name, index) => {
    runtime[`VITE_${name}_SERVICE_URL`] = mode === 'local'
      ? `http://10.0.2.16:${8010 + index}` : `https://customer.example/depo/${paths[index]}`;
  });
  globalThis.window = { location: { hostname: '10.0.2.16' }, DEPO_RUNTIME_CONFIG: runtime };
  // Simulate stale build-time loopback and gateway values. Runtime must win.
  globalThis.__DEPO_TEST_VITE_ENV__ = { VITE_API_GATEWAY_URL: 'https://old.example', VITE_GRAPH_SERVICE_URL: 'http://127.0.0.1:8013' };
  const module = await import(`data:text/javascript;base64,${Buffer.from(source + `\n// ${mode}`).toString('base64')}`);
  ids.forEach((id, index) => assert.equal(module.config.semanticServiceUrls[id], runtime[`VITE_${names[index]}_SERVICE_URL`]));
  const owners = {
    '/api/v1/qif/tasks': 'qif', '/api/v1/ontologies': 'ontology',
    '/api/v1/chat-stream': 'agentic', '/api/v1/workflows/bridge/previews': 'agentic',
    '/api/v1/graph/overview': 'graph', '/api/v1/governed-import': 'ingestion',
    '/api/v1/sysml-v2/import-commit': 'ingestion', '/api/v1/ontology/upload': 'ingestion',
    '/api/v1/oslc/remote/catalog': 'oslc', '/api/v1/catalog/products': 'catalog',
    '/api/v1/catalog/artifacts/retention': 'catalog', '/api/v1/data-products': 'dataProducts',
    '/api/v1/ceim/contract': 'ceim', '/api/v1/pipeline/jobs/runs': 'dataPipeline',
  };
  for (const [path, owner] of Object.entries(owners)) {
    assert.equal(module.getServiceForPath(path), owner, path);
    assert.equal(module.buildUrl(path), module.config.semanticServiceUrls[owner] + path);
  }
  assert.equal(module.API.agentic.health, '/healthz');
  assert.equal(module.buildSemanticServiceUrl('graph', '/api/v1/graph/overview'), runtime.VITE_GRAPH_SERVICE_URL + '/api/v1/graph/overview');
}
console.log('PASS: all ten browser routes in local/gateway mode; runtime overrides stale build configuration.');

const authSource = fs.readFileSync(new URL('../../frontend/src/services/serviceAuth.js', import.meta.url), 'utf8')
  .replace("import { config } from '../config';", "const config = globalThis.__DEPO_AUTH_TEST_CONFIG__;")
  .replace("import { operationForUrl } from './serviceContractRegistry';", 'const operationForUrl = () => null;');
globalThis.__DEPO_AUTH_TEST_CONFIG__ = { gatewayUrl: 'https://gateway.example/depo' };
globalThis.window.dispatchEvent = () => {};
const auth = await import(`data:text/javascript;base64,${Buffer.from(authSource).toString('base64')}`);
auth.setServiceAuthToken('fixture-read');
auth.setGatewaySubscriptionKey('fixture-subscription');
assert.equal(auth.serviceAuthHeaders('https://gateway.example/depo/graph')['Ocp-Apim-Subscription-Key'], 'fixture-subscription');
for (const target of ['https://evil.example/depo/graph', 'https://gateway.example/depox', 'https://gateway.example/depo/../outside', 'https://gateway.example/depo/a%2f..%2f../outside', 'https://user:secret@gateway.example/depo/graph']) {
  assert.equal(auth.serviceAuthHeaders(target)['Ocp-Apim-Subscription-Key'], undefined);
}
auth.clearServiceAuthToken();
assert.deepEqual(auth.serviceAuthHeaders(), {});
console.log('PASS: browser subscription scoping, path traversal isolation and credential clearing.');

// Run the dedicated Bridge interceptor with real serviceAuth scoping.
auth.setServiceAuthToken('fixture-read');
auth.setGatewaySubscriptionKey('fixture-subscription');
let bridgeInterceptor;
globalThis.__DEPO_BRIDGE_AXIOS__ = { create: () => ({ interceptors: { request: { use: fn => { bridgeInterceptor = fn; } } } }) };
globalThis.__DEPO_BRIDGE_AUTH__ = auth.serviceAuthHeaders;
const bridgeSource = fs.readFileSync(new URL('../../frontend/src/services/bridgeApi.js', import.meta.url), 'utf8')
  .replace("import axios from 'axios';", 'const axios = globalThis.__DEPO_BRIDGE_AXIOS__;')
  .replace("import { buildUrl } from '../config';", 'const buildUrl = path => path;')
  .replace("import { serviceAuthHeaders } from './serviceAuth';", 'const serviceAuthHeaders = globalThis.__DEPO_BRIDGE_AUTH__;');
await import(`data:text/javascript;base64,${Buffer.from(bridgeSource).toString('base64')}`);
const scoped = bridgeInterceptor({ url: 'https://gateway.example/depo/agentic/api/v1/workflows/bridge/previews', headers: { Authorization: 'Bearer explicit-read' } });
assert.equal(scoped.headers.Authorization, 'Bearer explicit-read');
assert.equal(scoped.headers['Ocp-Apim-Subscription-Key'], 'fixture-subscription');
assert.equal(bridgeInterceptor({ url: 'http://10.0.2.16:8012/api/v1/workflows/bridge/previews' }).headers['Ocp-Apim-Subscription-Key'], undefined);
auth.clearServiceAuthToken();
console.log('PASS: Bridge gateway subscription forwarding and explicit credential precedence.');
