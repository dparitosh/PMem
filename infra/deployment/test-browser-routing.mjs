// Dependency-free routing contract checks; execute with Node.js.
import fs from 'node:fs';
import assert from 'node:assert/strict';
const source = fs.readFileSync(new URL('../../frontend/src/config.js', import.meta.url), 'utf8')
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
  assert.equal(module.buildSemanticServiceUrl('graph', '/api/v1/graph/overview'), runtime.VITE_GRAPH_SERVICE_URL + '/api/v1/graph/overview');
}
console.log('PASS: all ten browser routes in local/gateway mode; runtime overrides stale build configuration.');

const authSource = fs.readFileSync(new URL('../../frontend/src/services/serviceAuth.js', import.meta.url), 'utf8')
  .replace("import { config } from '../config';", "const config = globalThis.__DEPO_AUTH_TEST_CONFIG__;");
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
