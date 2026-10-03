import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const scope = { URL, Map, Set, AbortController, TextDecoder, setTimeout, clearTimeout, fetch, serviceAuthHeaders: () => ({}) };
vm.createContext(scope);
for (const name of ['serviceContractRegistry', 'serviceDiscovery']) {
  const source = readFileSync(new URL(`../src/services/${name}.js`, import.meta.url), 'utf8').replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');
  vm.runInContext(source, scope);
}
const doc = (path, profile) => ({ openapi: '3.0.3', paths: { [path]: { get: { 'x-depo-authorization': { credential_profiles: [profile] } } } } });
scope.registerServiceContract('outer', 'http://example/gateway', doc('/graph/api/v1/graph/overview', 'ADMIN_API_KEY'));
scope.registerServiceContract('graph', 'http://example/gateway/graph', doc('/api/v1/graph/overview', 'GRAPH_READ_TOKEN'));
assert.equal(scope.operationForUrl('http://example/gateway/graph/api/v1/graph/overview').service, 'graph');
assert.equal(scope.operationForUrl('http://example/gateway/graph/missing'), null);
const failed = await scope.discoverServices({ graph: 'http://example/gateway/graph' }, async () => { throw new Error('offline'); });
assert.equal(failed[0].retainedContract, true);
assert.equal(failed[0].profiles[0], 'GRAPH_READ_TOKEN');
assert.equal(scope.operationForUrl('http://example/gateway/graph/api/v1/graph/overview').profiles[0], 'GRAPH_READ_TOKEN');
const malformed = await scope.discoverServices({ graph: 'http://example/gateway/graph' }, async () => new Response('invalid json'));
assert.equal(malformed[0].retainedContract, true);
assert.ok(scope.hasServiceContract('graph', 'http://example/gateway/graph'));
const changed = await scope.discoverServices({ graph: 'http://new-host' }, async () => { throw new Error('offline'); });
assert.equal(changed[0].retainedContract, false);
assert.equal(scope.operationForUrl('http://example/gateway/graph/api/v1/graph/overview').service, 'outer');
const refreshed = await scope.discoverServices({ graph: 'http://new-host' }, async () => new Response(JSON.stringify(doc('/api/v1/graph/access', 'GRAPH_READ_TOKEN'))));
assert.equal(refreshed[0].status, 'imported');
assert.equal(scope.operationForUrl('http://new-host/api/v1/graph/access').service, 'graph');
let cancelled = false;
const stream = new ReadableStream({ start(controller) {
  controller.enqueue(new Uint8Array(5 * 1024 * 1024));
  controller.enqueue(new Uint8Array(1));
}, cancel() { cancelled = true; } });
await assert.rejects(scope.readContractText(new Response(stream)), /exceeds size limit/);
assert.equal(cancelled, true);
await assert.rejects(scope.readContractText(new Response('x', { headers: { 'Content-Length': String(6 * 1024 * 1024) } })), /exceeds size limit/);
assert.equal(await scope.readContractText(new Response('unicode: é')), 'unicode: é');
console.log('PASS: nested ownership, failed/invalid refresh retention, root changes, successful refresh, streaming/header size limits and UTF-8');
