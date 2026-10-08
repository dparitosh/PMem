import { qualityRunsPayload, requirementsPayload } from './pagePayloads';

test('malformed quality run records are rejected before rendering', () => {
  for (const value of [{}, [null], [{ run_id: 'r', status: {} }], [{ run_id: 'r', output_manifest: [] }]]) {
    expect(() => qualityRunsPayload(value)).toThrow('invalid run list');
  }
  expect(qualityRunsPayload([{ run_id: 'r', status: 'completed', output_manifest: { counts: { accepted: 2 } } }])).toHaveLength(1);
});

test('requirements reject malformed collections, context links, and rendered values', () => {
  for (const value of [{}, [null], [{ id: 'r', context_links: {} }], [{ id: 'r', context_links: [null] }], [{ id: 'r', title: {} }]]) {
    expect(() => requirementsPayload(value)).toThrow('invalid requirement list');
  }
  expect(requirementsPayload([{ id: 'r', title: 'Requirement', context_links: [{ type: 'SATISFIES', other: 'Part' }] }])).toHaveLength(1);
  expect(requirementsPayload([])).toEqual([]);
});
