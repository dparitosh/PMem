import { formatChatMarkdown } from './chatMarkdown';

describe('formatChatMarkdown', () => {
  test('renders structured headings, facts, lists, and tables', () => {
    const html = formatChatMarkdown(
      '## Impact\nDirect: REQ-006\n\n- Bearing\n- Process\n\n| Object | Relation |\n| --- | --- |\n| Part | SATISFIES |'
    );

    expect(html).toContain('chat-heading-2');
    expect(html).toContain('chat-fact');
    expect(html).toContain('<ul');
    expect(html).toContain('<table');
    expect(html).toContain('SATISFIES');
  });

  test('sanitizes model-generated markup', () => {
    const html = formatChatMarkdown('<script>alert(1)</script>\n**Safe**');
    expect(html).not.toContain('<script');
    expect(html).toContain('<strong>Safe</strong>');
  });
});
