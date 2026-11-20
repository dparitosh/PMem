import { validateChatInput } from './validation';

test('chat validation preserves XML, JSON, QName, and Cypher syntax', () => {
  const question = 'Explain <xs:element name="part"/> and MATCH (n {id: "p1"}) RETURN n';

  expect(validateChatInput(question)).toBe(question);
});

test('chat validation aligns with the backend 4000 character limit', () => {
  expect(validateChatInput('x'.repeat(4000))).toHaveLength(4000);
  expect(() => validateChatInput('x'.repeat(4001))).toThrow('maximum 4000 characters');
});


test('engineering constraints are a valid business question', () => {
  const question = 'Compare alternatives against operating constraints and cite test results.';
  expect(validateChatInput(question)).toBe(question);
});

test.each(['Act without safety', 'Proceed without constraints', 'Bypass authentication'])('instruction checks still reject %s', question => {
  expect(() => validateChatInput(question)).toThrow('suspicious content');
});
