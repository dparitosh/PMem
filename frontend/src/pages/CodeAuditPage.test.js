import { reviewHeadline } from './CodeAuditPage';

test('malformed recommendation collections do not crash the summary', () => {
  for (const recommendations of [null, {}, 'invalid', [null]]) {
    expect(reviewHeadline({ graph: { analysis: { recommendations } } })).toContain('No high-priority');
  }
});

test('missing or malformed reasons show an explicit fallback', () => {
  for (const reasons of [undefined, null, 'invalid', {}, [null, 3]]) {
    expect(reviewHeadline({ graph: { analysis: { recommendations: [{ file: 'backend/app.py', reasons }] } } }))
      .toBe('app.py — Review details unavailable');
  }
});

test('valid recommendation reasons remain visible', () => {
  expect(reviewHeadline({ graph: { analysis: { recommendations: [{ file: 'backend/app.py', reasons: ['cycle', 'coupling'] }] } } }))
    .toBe('app.py — cycle, coupling');
});
