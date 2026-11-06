import { validateChatInput } from './validation';

test('chat validation preserves XML, JSON, QName, and Cypher syntax', () => {
  const question = 'Explain <xs:element name="part"/> and MATCH (n {id: "p1"}) RETURN n';

  expect(validateChatInput(question)).toBe(question);
});

test('chat validation aligns with the backend 4000 character limit', () => {
  expect(validateChatInput('x'.repeat(4000))).toHaveLength(4000);
  expect(() => validateChatInput('x'.repeat(4001))).toThrow('maximum 4000 characters');
});
