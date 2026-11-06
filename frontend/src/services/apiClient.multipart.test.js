import { prepareMultipartHeaders, apiClient, ontologyAPI } from './apiClient';
import { vi } from 'vitest';

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

test('source-only schema registration sends every original companion and relative path', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({data:{status:'success'}});
  try {
    const controller = new AbortController();
    const sources = [new File(['one'],'one.xsd'), new File(['two'],'two.xsd')];
    await ontologyAPI.upload(new File(['wrapper'],'set.xsd'), {generationType:'as_is'}, 'test',
      {signal:controller.signal, dependencies:sources, dependencyPaths:['Apps/one.xsd','Library/two.xsd']});
    const form = post.mock.calls[0][1];
    expect(form.getAll('dependencies').map(file => file.name)).toEqual(['one.xsd','two.xsd']);
    expect(JSON.parse(form.get('dependency_paths'))).toEqual(['Apps/one.xsd','Library/two.xsd']);
    expect(post.mock.calls[0][2].signal).toBe(controller.signal);
  } finally {post.mockRestore();}
});
