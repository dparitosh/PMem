import { prepareMultipartHeaders } from './apiClient';

test('multipart upload clears inherited JSON content type and preserves credentials', () => {
  const request = { data: new FormData(), headers: { 'Content-Type': 'application/json', Authorization: 'Bearer fixture' } };
  prepareMultipartHeaders(request);
  expect(request.headers['Content-Type']).toBeUndefined();
  expect(request.headers.Authorization).toBe('Bearer fixture');
});

test('ordinary JSON requests retain their content type', () => {
  const request = { data: { message: 'example' }, headers: { 'Content-Type': 'application/json' } };
  prepareMultipartHeaders(request);
  expect(request.headers['Content-Type']).toBe('application/json');
});

test('AxiosHeaders deletion also removes explicit multipart headers without a boundary', () => {
  const values = new Map([['Content-Type', 'multipart/form-data']]);
  const request = { data: new FormData(), headers: { delete: key => values.delete(key) } };
  prepareMultipartHeaders(request);
  expect(values.has('Content-Type')).toBe(false);
});
