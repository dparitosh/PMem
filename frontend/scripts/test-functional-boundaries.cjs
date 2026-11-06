// Run with Node; no frontend dependency installation required.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, 'src', file), 'utf8');
let clock = Date.now();
class Clock extends Date { static now() { return clock; } }
const timers = new Map(), events = [];
let sequence = 0;
const context = vm.createContext({ Date: Clock, Event, config: {}, operationForUrl: () => null,
  window: { dispatchEvent: event => events.push(event.type) },
  setTimeout: callback => { const id = ++sequence; timers.set(id, callback); return id; },
  clearTimeout: id => timers.delete(id) });
vm.runInContext(read('services/serviceAuth.js').replace(/^import .*;\r?$/gm, '').replace(/export /g, ''), context);
context.setCredentialProfile('ADMIN_API_KEY', 'separate-admin');
context.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_one');
context.setCredentialProfile('INGESTION_WRITE_TOKEN', 'depo_session_one');
context.setBrowserSessionExpiry('depo_session_one', new Date(clock + 1000).toISOString());
context.expireBrowserSession('depo_session_other');
assert.equal(context.getCredentialProfile('GRAPH_READ_TOKEN'), 'depo_session_one');
clock += 2000;
context.serviceAuthHeaders('/api/v1/graph/overview');
assert.equal(context.getCredentialProfile('GRAPH_READ_TOKEN'), '');
assert.equal(context.getCredentialProfile('INGESTION_WRITE_TOKEN'), '');
assert.equal(context.getCredentialProfile('ADMIN_API_KEY'), 'separate-admin');
assert.ok(events.includes('depo:session-expired'));
assert.throws(() => context.setBrowserSessionExpiry('depo_session_one', 'invalid'));
context.setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_new');
context.setBrowserSessionExpiry('depo_session_new', new Date(clock + 1000).toISOString());
context.expireBrowserSession('depo_session_one');
assert.equal(context.getCredentialProfile('GRAPH_READ_TOKEN'), 'depo_session_new');
context.clearServiceAuthToken();
assert.equal(timers.size, 0);

vm.runInContext(read('utils/ontologyRegistry.js').replace(/export /g, ''), context);
const rows = context.normalizeOntologyRows([
  { ontology_id: 'qif_v1', prefix: 'qif', ontology_name: 'First', created_at: '2026-01-01' },
  { ontology_id: 'qif_v2', prefix: 'qif', ontology_name: 'Second' }]);
assert.equal(rows.length, 2);
assert.notEqual(rows[0].value, rows[1].value);
assert.equal(rows[0].label, 'First');
assert.equal(rows[0].created_at, '2026-01-01');
const mapper = read('Components/OntologyMapper.js');
const optionsStart = mapper.indexOf('const buildOntologyOptions = useCallback(');
const optionsEnd = mapper.indexOf('}, []);', optionsStart) + '}, []);'.length;
context.useCallback = callback => callback;
context.normalizeSourceFormat = () => 'xml';
vm.runInContext(mapper.slice(optionsStart, optionsEnd) + '\nglobalThis.buildOntologyOptions = buildOntologyOptions;', context);
const options = context.buildOntologyOptions(rows);
assert.equal(options.length, 2);
assert.equal(options[0].value, 'qif_v1');
assert.equal(options[1].value, 'qif_v2');
vm.runInContext(read('utils/ontologyEvents.js').replace(/export /g, ''), context);
const eventCount = events.length;
context.notifyOntologyChange({ config: { method: 'post', url: 'http://app:8014/api/v1/engineering-workflows' }, data: { status: 'policy_blocked' } });
assert.equal(events.length, eventCount);
context.notifyOntologyChange({ config: { method: 'post', url: 'http://app:8014/api/v1/engineering-workflows' }, data: { status: 'registered' } });
assert.equal(events.at(-1), 'depo:ontologies-changed');

const config = read('config.js');
context.serviceForContractPath = () => null;
vm.runInContext(config.slice(config.indexOf('const SERVICE_PATHS = ['), config.indexOf('// Deprecated:')).replace(/export /g, ''), context);
vm.runInContext('globalThis.getServiceForPath = getServiceForPath;', context);
assert.equal(context.getServiceForPath('/api/v1/ontology/qif_v1/data-dictionary'), 'ingestion');
assert.equal(context.getServiceForPath('/api/v1/llm/health'), 'agentic');
assert.equal(context.getServiceForPath('/api/v1/catalog/products'), 'catalog');
vm.runInContext(read('utils/apiErrorMessage.js').replace(/export /g, ''), context);
assert.match(context.apiErrorMessage({ response: { status: 401 } }), /Reconnect/);
assert.match(context.apiErrorMessage({ code: 'ECONNABORTED' }), /timed out/);
assert.ok(!context.apiErrorMessage({ response: { data: { detail: [{ input: 'secret-value' }] } } }).includes('secret-value'));
console.log('PASS: session expiry, credential isolation, registry identity, route ownership and safe error classification');
