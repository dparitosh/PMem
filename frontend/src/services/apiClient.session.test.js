import { clearClientSessionId, getClientSessionId, setClientSessionId } from './apiClient';

test('chat sessions are server-issued and can be explicitly cleared', () => {
  window.sessionStorage.clear();

  expect(getClientSessionId()).toBeNull();
  expect(window.sessionStorage.length).toBe(0);

  setClientSessionId('server-session');
  expect(getClientSessionId()).toBe('server-session');

  clearClientSessionId();
  expect(getClientSessionId()).toBeNull();
});
