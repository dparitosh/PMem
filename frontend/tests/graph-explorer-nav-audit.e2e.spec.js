const { test } = require('@playwright/test');

test('audit graph explorer actual page state', async ({ page }) => {
  const logs = [];
  page.on('console', (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));

  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  await page.setViewportSize({ width: 1600, height: 1000 });

  const openPlatform = page.getByRole('button', { name: /open platform/i });
  if (await openPlatform.count()) {
    await openPlatform.first().click();
    await page.waitForLoadState('networkidle');
  }

  const graphNav = page.getByRole('link', { name: /graph explorer/i }).or(
    page.getByRole('button', { name: /graph explorer/i })
  );
  if (await graphNav.count()) {
    await graphNav.first().click();
    await page.waitForLoadState('networkidle');
  }

  await page.screenshot({ path: '../tmp-graph-explorer-nav-audit.png', fullPage: true });

  const toolbarTexts = await page.locator('button, input, select').evaluateAll((els) =>
    els.map((el) => ({
      tag: el.tagName,
      text: (el.innerText || el.value || '').trim(),
      aria: el.getAttribute('aria-label'),
      title: el.getAttribute('title'),
    }))
  );

  const textLabels = await page.locator('svg text').allInnerTexts().catch(() => []);
  const circleCount = await page.locator('svg circle').count().catch(() => 0);
  const pathCount = await page.locator('svg path').count().catch(() => 0);
  const lineCount = await page.locator('svg line').count().catch(() => 0);
  const bodyText = await page.locator('body').innerText();

  console.log('URL:', page.url());
  console.log('Toolbar controls:', JSON.stringify(toolbarTexts, null, 2));
  console.log('SVG text count:', textLabels.length);
  console.log('SVG text sample:', JSON.stringify(textLabels.slice(0, 40), null, 2));
  console.log('SVG circle count:', circleCount);
  console.log('SVG path count:', pathCount);
  console.log('SVG line count:', lineCount);
  console.log('Body text sample:', bodyText.slice(0, 3000));
  console.log('Console logs:', JSON.stringify(logs.slice(-40), null, 2));
});
