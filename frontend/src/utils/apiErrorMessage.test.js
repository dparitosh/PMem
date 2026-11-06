import { apiErrorMessage, apiRequestId } from './apiErrorMessage';

test('does not render FastAPI validation objects or submitted values', () => {
  const error = { response: { data: { detail: [{ msg: 'invalid', input: 'secret-token' }] } } };
  const message = apiErrorMessage(error);
  expect(message).toContain('Invalid request');
  expect(message).not.toContain('secret-token');
});

test('preserves a plain service error message', () => {
  expect(apiErrorMessage({ response: { data: { detail: 'Job was not found' } } })).toBe('Job was not found');
});

test.each([
  { headers: { 'x-request-id': 'request-123' }, data: { detail: 'Unavailable' } },
  { headers: new Headers({ 'X-Request-ID': 'request-123' }), data: { detail: 'Unavailable' } },
  { data: { detail: 'Unavailable', request_id: 'request-123' } },
])('includes a safe server request ID in user-facing diagnostics', response => {
  expect(apiErrorMessage({ response })).toBe('Unavailable Request ID: request-123');
});

test('rejects unsafe IDs and does not echo validation input', () => {
  const error = { response: { data: { request_id: 'secret\nvalue', detail: [{ input: 'private-key' }] } } };
  expect(apiRequestId(error)).toBe('');
  expect(apiErrorMessage(error)).not.toMatch(/private-key|secret/);
  expect(apiErrorMessage({ response: { headers: { 'x-request-id': 'req-1' }, data: { detail: 'Failed Request ID: req-1' } } })).toBe('Failed Request ID: req-1');
});

test('network diagnostics identify the origin without leaking URL credentials or queries', () => {
  const message = apiErrorMessage({code:'ERR_NETWORK', config:{url:'http://user:private@service.example:8014/api/v1/ontology/registered?token=secret'}});
  expect(message).toContain('http://service.example:8014');
  expect(message).toContain('cannot distinguish');
  expect(message).not.toMatch(/private|secret|token=|user:/);
});

test('offline diagnostics do not suggest rotating credentials', () => {
  const original = Object.getOwnPropertyDescriptor(window.navigator, 'onLine');
  Object.defineProperty(window.navigator, 'onLine', {value:false, configurable:true});
  try { expect(apiErrorMessage({code:'ERR_NETWORK'})).toContain('browser is offline'); }
  finally { if (original) Object.defineProperty(window.navigator, 'onLine', original); else delete window.navigator.onLine; }
});

test('HTTPS to HTTP routing reports mixed content instead of a key problem', () => {
  vi.stubGlobal('window', {location:{protocol:'https:',href:'https://portal.example/'}});
  try {
    const message = apiErrorMessage({code:'ERR_NETWORK',config:{url:'http://service.example:8014/api/v1/ontology/registered'}});
    expect(message).toContain('HTTPS page is targeting an HTTP service');
    expect(message).not.toContain('credential');
  } finally { vi.unstubAllGlobals(); }
});
