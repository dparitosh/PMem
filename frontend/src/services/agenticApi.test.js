import { agenticClient } from './agenticApi';
import { clearServiceAuthToken, setServiceAuthToken } from './serviceAuth';

afterEach(() => clearServiceAuthToken());

test('a scoped ontology-agent token takes precedence over the app token', () => {
  setServiceAuthToken('app-token');
  const request = { headers: { Authorization: 'Bearer ontology-read-token' } };
  const configured = agenticClient.interceptors.request.handlers[0].fulfilled(request);
  expect(configured.headers.Authorization).toBe('Bearer ontology-read-token');
});

test('the app token is used when a request has no scoped token', () => {
  setServiceAuthToken('app-token');
  const configured = agenticClient.interceptors.request.handlers[0].fulfilled({ headers: {} });
  expect(configured.headers.Authorization).toBe('Bearer app-token');
});
