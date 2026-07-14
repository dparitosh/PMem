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
