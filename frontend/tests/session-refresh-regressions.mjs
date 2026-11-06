import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const storage = new Map();
const source = readFileSync(new URL('../src/services/serviceAuth.js', import.meta.url), 'utf8').replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');
function load(root = 'http://service') {
  const scope = { Map, Date, Event, URL, setTimeout: () => 1, clearTimeout: () => {},
    config: { semanticServiceUrls: { graph: root } }, operationForUrl: () => null,
    window: { dispatchEvent: () => {}, sessionStorage: {
      getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key),
    } } };
  vm.createContext(scope); vm.runInContext(source, scope); return scope;
}
let scope = load();
scope.setCredentialProfile('ADMIN_API_KEY', 'raw-admin-secret');
scope.setCredentialProfile('CATALOG_SERVICE_TOKEN', 'raw-service-secret');
assert.equal(storage.size, 0);
scope.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_fixture');
scope.setCredentialProfile('INGESTION_WRITE_TOKEN', 'depo_session_fixture');
scope.setBrowserSessionExpiry('depo_session_fixture', new Date(Date.now() + 600000).toISOString());
assert.equal(storage.size, 1);
assert.ok(![...storage.values()][0].includes('raw-admin-secret'));
assert.ok(![...storage.values()][0].includes('raw-service-secret'));
scope = load();
assert.equal(scope.getBrowserSessionStatus().profiles.length, 2);
assert.equal(scope.serviceAuthHeaders('http://service/read').Authorization, 'Bearer depo_session_fixture');
assert.equal(scope.getCredentialProfile('INGESTION_WRITE_TOKEN'), 'depo_session_fixture');
assert.equal(scope.getCredentialProfile('ADMIN_API_KEY'), '');
scope.expireBrowserSession('depo_session_fixture');
assert.equal(storage.size, 0);
assert.equal(load().getServiceAuthToken(), '');
scope.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_fixture');
scope.setBrowserSessionExpiry('depo_session_fixture', new Date(Date.now() + 600000).toISOString());
assert.equal(load('http://different-service').getServiceAuthToken(), '');
assert.equal(storage.size, 0);
storage.set('depo.browserSession.v1', '{broken');
assert.equal(load().getServiceAuthToken(), '');
assert.equal(storage.size, 0);
scope = load();
scope.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_fixture');
scope.setBrowserSessionExpiry('depo_session_fixture', new Date(Date.now() + 600000).toISOString());
const saved = JSON.parse([...storage.values()][0]);
saved.deadline = Date.now() + 3600000;
storage.set('depo.browserSession.v1', JSON.stringify(saved));
assert.equal(load().getServiceAuthToken(), '');
assert.equal(storage.size, 0);
scope.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_fixture');
scope.setBrowserSessionExpiry('depo_session_fixture', new Date(Date.now() + 600000).toISOString());
scope.clearServiceAuthToken();
assert.equal(load().getServiceAuthToken(), '');
console.log('PASS: refresh restores only delegated scopes; expiry, malformed records and changed service roots clear storage');
