import { beforeEach, afterEach, expect, test, vi } from 'vitest';
import { clearServiceAuthToken, getCredentialProfile, setCredentialProfile, setBrowserSessionExpiry, serviceAuthHeaders, requireServiceReadAccess } from './serviceAuth';
import { registerServiceContract, clearServiceContracts } from './serviceContractRegistry';

vi.mock('../config', () => ({ config: { semanticServiceUrls: {
  graph: 'http://vm:8013', agentic: 'http://vm:8012', catalog: 'http://vm:8016', dataProducts: 'http://vm:8017',
} } }));
const reads = [
  ['graph', 'http://vm:8013', '/api/v1/graph/metrics'],
  ['agentic', 'http://vm:8012', '/api/v1/observability/summary'],
  ['catalog', 'http://vm:8016', '/api/v1/catalog/products'],
  ['dataProducts', 'http://vm:8017', '/api/v1/data-products'],
];
beforeEach(() => { clearServiceAuthToken(); clearServiceContracts(); });
afterEach(() => { clearServiceAuthToken(); vi.useRealTimers(); });

test('credential replacement and sign-out clear pending publication recovery', () => {
  sessionStorage.setItem('depo:pending-publication:old', 'old-request');
  sessionStorage.setItem('unrelated', 'preserved');
  setCredentialProfile('DATA_PRODUCT_APPROVAL_TOKEN', 'replacement');
  expect(sessionStorage.getItem('depo:pending-publication:old')).toBeNull();
  sessionStorage.setItem('depo:pending-publication:new', 'new-request');
  clearServiceAuthToken();
  expect(sessionStorage.getItem('depo:pending-publication:new')).toBeNull();
  expect(sessionStorage.getItem('unrelated')).toBe('preserved');
  sessionStorage.removeItem('unrelated');
});

test.each(reads)('%s keeps read authorization after importing a contract without profile metadata', (service, base, path) => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_test');
  registerServiceContract(service, base, { openapi: '3.0.3', paths: { [path]: { get: { security: [{ BearerKey: [] }] } } } });
  const request = { url: `${base}${path}?ontology_id=`, method: 'get', headers: serviceAuthHeaders(`${base}${path}`) };
  expect(request.headers.Authorization).toBe('Bearer depo_session_test');
  expect(() => requireServiceReadAccess(request)).not.toThrow();
});

test('admin-only access and expired sessions do not send anonymous protected reads', () => {
  vi.useFakeTimers();
  const url = 'http://vm:8013/api/v1/graph/metrics';
  setCredentialProfile('ADMIN_API_KEY', 'admin-only');
  expect(() => requireServiceReadAccess({ url, headers: serviceAuthHeaders(url) })).toThrow(/Connect registered services/);
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_test');
  setBrowserSessionExpiry('depo_session_test', new Date(Date.now() + 900000).toISOString());
  vi.advanceTimersByTime(900001);
  expect(() => requireServiceReadAccess({ url, headers: serviceAuthHeaders(url) })).toThrow(/expired/);
  expect(() => requireServiceReadAccess({ url, headers: { Authorization: 'Bearer explicit-read' } })).not.toThrow();
});

test('public operations, unrelated hosts and writes are not treated as the four protected reads', () => {
  for (const url of ['http://vm:8013/health', 'http://other/api/v1/graph/metrics']) {
    expect(() => requireServiceReadAccess({ url, headers: {} })).not.toThrow();
  }
  expect(() => requireServiceReadAccess({ url: reads[3][1] + reads[3][2], method: 'post', headers: {} })).not.toThrow();
});

test('credentials never follow an unconfigured host, embedded userinfo, or encoded traversal', () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-secret');
  expect(serviceAuthHeaders('http://vm:8013/api/v1/graph/metrics').Authorization).toBe('Bearer read-secret');
  for (const endpoint of ['http://other/read', 'http://user@vm:8013/read', 'http://vm:8013/%2e%2e%2fread']) {
    expect(serviceAuthHeaders(endpoint)).toEqual({});
  }
});

test('replacing a delegated read credential clears its delegated write scopes', () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'depo_session_old');
  setCredentialProfile('INGESTION_WRITE_TOKEN', 'depo_session_old');
  setBrowserSessionExpiry('depo_session_old', new Date(Date.now() + 600000).toISOString());
  setCredentialProfile('GRAPH_READ_TOKEN', 'new-read');
  expect(serviceAuthHeaders('http://vm:8013/api/v1/graph/metrics').Authorization).toBe('Bearer new-read');
  expect(getCredentialProfile('INGESTION_WRITE_TOKEN')).toBe('');
});

test('session expiry rejected by restoration is also rejected before installation', () => {
  expect(() => setBrowserSessionExpiry('depo_session_bad', new Date(Date.now() + 3600000).toISOString())).toThrow(/fifteen minutes/);
});
