import { apiErrorMessage } from './apiErrorMessage';

test('does not render FastAPI validation objects or submitted values', () => {
  const error = { response: { data: { detail: [{ msg: 'invalid', input: 'secret-token' }] } } };
  const message = apiErrorMessage(error);
  expect(message).toContain('Invalid request');
  expect(message).not.toContain('secret-token');
});

test('preserves a plain service error message', () => {
  expect(apiErrorMessage({ response: { data: { detail: 'Job was not found' } } })).toBe('Job was not found');
});
