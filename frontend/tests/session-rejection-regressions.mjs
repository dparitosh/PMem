import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const events = [];
const scope = { Map, Date, Event, URL, setTimeout: () => 1, clearTimeout: () => {},
  window: { dispatchEvent: event => events.push(event.type) },
  config: { semanticServiceUrls: { graph: 'http://service' } }, operationForUrl: () => null };
vm.createContext(scope);
const source = readFileSync(new URL('../src/services/serviceAuth.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '').replace(/export /g, '');
vm.runInContext(source, scope);
const token = 'depo_session_fixture';
const connect = () => {
  scope.setCredentialProfile('GRAPH_READ_TOKEN', token);
  scope.setCredentialProfile('INGESTION_WRITE_TOKEN', token);
  scope.setBrowserSessionExpiry(token, new Date(Date.now() + 600000).toISOString());
};
connect();
assert.equal(scope.serviceAuthHeaders('http://service/read').Authorization, `Bearer ${token}`);
scope.handleSessionRejection(403, `Bearer ${token}`, 'Policy forbids this operation');
assert.equal(scope.getCredentialProfile('GRAPH_READ_TOKEN'), token);
scope.handleSessionRejection(403, 'Bearer depo_session_old', 'Browser session scope is unavailable or credentials changed; reconnect in Admin');
assert.equal(scope.getCredentialProfile('GRAPH_READ_TOKEN'), token);
scope.handleSessionRejection(403, `Bearer ${token}`, 'Browser session scope is unavailable or credentials changed; reconnect in Admin');
assert.equal(scope.getCredentialProfile('GRAPH_READ_TOKEN'), '');
assert.equal(scope.getCredentialProfile('INGESTION_WRITE_TOKEN'), '');
assert.ok(events.includes('depo:session-expired'));
connect();
scope.handleSessionRejection(401, `Bearer ${token}`);
assert.equal(scope.getCredentialProfile('GRAPH_READ_TOKEN'), '');
console.log('PASS: scoped session rejection and credential clearing');
