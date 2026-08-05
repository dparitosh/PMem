import { replaceParams } from './config';

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
    jest.resetModules();
  });

  test('keeps agentic requests disabled even when a service URL is present', () => {
    process.env.REACT_APP_AGENTIC_ENABLED = 'false';
    process.env.REACT_APP_AGENTIC_SERVICE_URL = 'http://127.0.0.1:8012';
    jest.resetModules();

    const { config } = require('./config');
    expect(config.agenticEnabled).toBe(false);
    expect(config.agenticServiceUrl).toBe('');
  });

  test('exposes the configured service URL only when explicitly enabled', () => {
    process.env.REACT_APP_AGENTIC_ENABLED = 'true';
    process.env.REACT_APP_AGENTIC_SERVICE_URL = 'http://127.0.0.1:8012';
    jest.resetModules();

    const { config } = require('./config');
    expect(config.agenticEnabled).toBe(true);
    expect(config.agenticServiceUrl).toBe('http://127.0.0.1:8012');
  });
});

test('normalizes a trailing slash from the configured backend URL', () => {
  const original = process.env.REACT_APP_BACKEND_URL;
  process.env.REACT_APP_BACKEND_URL = 'https://api.example.test/';
  jest.resetModules();

  const { config } = require('./config');
  expect(config.backendUrl).toBe('https://api.example.test');

  if (original === undefined) delete process.env.REACT_APP_BACKEND_URL;
  else process.env.REACT_APP_BACKEND_URL = original;
  jest.resetModules();
});
