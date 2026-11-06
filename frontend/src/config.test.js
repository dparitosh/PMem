import { vi } from 'vitest';
import { buildUrl, getServiceForPath, replaceParams } from './config';

test('encodes path parameters and replaces repeated placeholders', () => {
  expect(replaceParams('/ontology/{id}/links/{id}', { id: 'domain model/a' }))
    .toBe('/ontology/domain%20model%2Fa/links/domain%20model%2Fa');
});

test('preserves nested artifact separators while encoding each path segment', () => {
  expect(replaceParams('/jobs/{task}/{path}', {
    task: 'job 1',
    path: 'reports/July output?.json',
  }, { pathParams: ['path'] })).toBe('/jobs/job%201/reports/July%20output%3F.json');
});

describe('optional agentic service configuration', () => {
  const originalEnabled = process.env.REACT_APP_AGENTIC_ENABLED;
  const originalUrl = process.env.REACT_APP_AGENTIC_SERVICE_URL;

  afterEach(() => {
    if (originalEnabled === undefined) delete process.env.REACT_APP_AGENTIC_ENABLED;
    else process.env.REACT_APP_AGENTIC_ENABLED = originalEnabled;
    if (originalUrl === undefined) delete process.env.REACT_APP_AGENTIC_SERVICE_URL;
    else process.env.REACT_APP_AGENTIC_SERVICE_URL = originalUrl;
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  test('keeps agentic requests disabled even when a service URL is present', async () => {
    vi.stubEnv('REACT_APP_AGENTIC_ENABLED', 'false');
    vi.stubEnv('REACT_APP_AGENTIC_SERVICE_URL', 'http://127.0.0.1:8012');
    vi.resetModules();

    const { config } = await import('./config');
    expect(config.agenticEnabled).toBe(false);
    expect(config.agenticServiceUrl).toBe('');
  });

  test('exposes the configured service URL only when explicitly enabled', async () => {
    vi.stubEnv('REACT_APP_AGENTIC_ENABLED', 'true');
    vi.stubEnv('REACT_APP_AGENTIC_SERVICE_URL', 'http://127.0.0.1:8012');
    vi.resetModules();

    const { config } = await import('./config');
    expect(config.agenticEnabled).toBe(true);
    expect(config.agenticServiceUrl).toBe('http://127.0.0.1:8012');
  });
});

test('normalizes a trailing slash from the configured backend URL', async () => {
  const original = process.env.REACT_APP_BACKEND_URL;
  vi.stubEnv('REACT_APP_BACKEND_URL', 'https://api.example.test/');
  vi.resetModules();

  const { config } = await import('./config');
  expect(config.backendUrl).toBe('https://api.example.test');

  if (original === undefined) delete process.env.REACT_APP_BACKEND_URL;
  else process.env.REACT_APP_BACKEND_URL = original;
  vi.unstubAllEnvs();
  vi.resetModules();
});

test('does not expose API credentials through browser configuration', async () => {
  vi.stubEnv('REACT_APP_API_TOKEN', 'must-not-reach-the-browser');
  vi.stubEnv('REACT_APP_ADMIN_API_KEY', 'must-not-reach-the-browser');
  vi.resetModules();

  const { config } = await import('./config');
  expect(config).not.toHaveProperty('apiToken');
  expect(config).not.toHaveProperty('adminApiKey');

  vi.unstubAllEnvs();
  vi.resetModules();
});

test('routes published service contracts to their owning local service', () => {
  expect(getServiceForPath('/api/v1/qif/catalog')).toBe('qif');
  expect(getServiceForPath('/api/v1/ontologies/capabilities')).toBe('ontology');
  expect(getServiceForPath('/api/v1/ontology/ap242/data-dictionary')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/ontology/registered')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/ontology/ap242/taxonomy')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/ap242/inspect')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/documents/jobs')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/reports/xsd-relational')).toBe('ingestion');
  expect(getServiceForPath('/api/v1/oslc/health')).toBe('oslc');
  expect(getServiceForPath('/api/v1/ceim/contract')).toBe('ceim');
  expect(getServiceForPath('/api/v1/graphql')).toBe('graph');
  expect(getServiceForPath('/api/v1/sparql/federation/peers')).toBe('graph');
  expect(getServiceForPath('/api/v1/observability/summary')).toBe('agentic');
  expect(buildUrl('/api/v1/qif/catalog')).toContain(':8010/api/v1/qif/catalog');
});

test('uses direct service roots when an API gateway is not configured', () => {
  expect(buildUrl('/api/v1/graph/health')).toContain(':8013/api/v1/graph/health');
});

test.each([
  ['/api/v1/ontologies?limit=200&offset=0', 'ontology', 8011],
  ['/api/v1/ontology/registered?limit=200', 'ingestion', 8014],
  ['/api/v1/catalog/products?offset=20', 'catalog', 8016],
  ['/api/v1/graph?limit=10&filter=a%2Fb', 'graph', 8013],
])('routes initial requests with query parameters: %s', (endpoint, service, port) => {
  // Before Admin discovers OpenAPI contracts, prefix routing must still choose
  // the owning service and preserve the complete query for the request.
  expect(getServiceForPath(endpoint)).toBe(service);
  expect(buildUrl(endpoint)).toContain(`:${port}${endpoint}`);
});

test('does not match similarly named namespaces when routing query parameters', () => {
  expect(getServiceForPath('/api/v1/ontologies-extra?limit=200')).toBeNull();
});
