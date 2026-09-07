import { expect, test } from 'vitest';
import { buildTooltipHeader } from './tooltipBuilder';

test('escapes imported graph labels before producing tooltip HTML', () => {
  const html = buildTooltipHeader('<img src=x onerror=alert(1)>');

  expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
  expect(html).not.toContain('<span><img');
});
