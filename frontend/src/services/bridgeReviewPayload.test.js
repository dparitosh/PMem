import { bridgeReviewPayload } from './bridgeReviewPayload';

test('rejects malformed collections and rendered fields', () => {
  for (const result of [
    { alignment_items: {} }, { alignment_candidates: 'invalid' },
    { alignment_items: [{ source: {}, unresolved_checks: [] }] },
    { alignment_items: [{ unresolved_checks: [null] }] },
    { llm: { review: { questions: {}, limitations: 'review' } } },
    { llm: { review: { questions: [{ question: 'Review?', evidence_iris: {} }], limitations: 'review' } } },
  ]) expect(() => bridgeReviewPayload({ steps: [{ result }] })).toThrow('invalid response');
  expect(() => bridgeReviewPayload({ steps: {} })).toThrow();
});

test('accepts empty and grounded review responses', () => {
  const response = { steps: [{ result: { alignment_candidates: [], alignment_items: [],
    llm: { review: { questions: [{ question: 'Compatible?', evidence_iris: ['urn:Part'] }], limitations: 'Review only' } } } }] };
  expect(bridgeReviewPayload(response)).toBe(response);
  expect(bridgeReviewPayload({ steps: [] }).steps).toEqual([]);
});
