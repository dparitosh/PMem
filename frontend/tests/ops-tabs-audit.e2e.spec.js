const { test } = require('@playwright/test');

async function openPlatform(page) {
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  await page.setViewportSize({ width: 1600, height: 1000 });
  const openPlatform = page.getByRole('button', { name: /open platform/i });
  if (await openPlatform.count()) {
    await openPlatform.first().click();
    await page.waitForLoadState('networkidle');
  }
}

async function dumpTabState(page, tabName, screenshotName) {
  const tabButton = page.getByRole('button', { name: new RegExp(tabName, 'i') });
  await tabButton.first().click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  const bodyText = await page.locator('body').innerText();
  const buttons = await page.locator('button').evaluateAll((els) =>
    els.map((el) => ({
      text: (el.innerText || '').trim(),
      aria: el.getAttribute('aria-label'),
      title: el.getAttribute('title'),
      disabled: el.hasAttribute('disabled'),
    }))
  );
  const selects = await page.locator('select').evaluateAll((els) =>
    els.map((el) => ({
      value: el.value,
      title: el.getAttribute('title'),
      aria: el.getAttribute('aria-label'),
      options: Array.from(el.options).map((opt) => opt.textContent.trim()).slice(0, 20),
    }))
  ).catch(() => []);
  const inputs = await page.locator('input').evaluateAll((els) =>
    els.map((el) => ({
      type: el.type,
      value: el.value,
      placeholder: el.getAttribute('placeholder'),
      aria: el.getAttribute('aria-label'),
    }))
  ).catch(() => []);
  const alerts = await page.locator('[role=\"alert\"], .alert, .MuiAlert-root').allInnerTexts().catch(() => []);
  const tables = await page.locator('table').count().catch(() => 0);
  const svgText = await page.locator('svg text').allInnerTexts().catch(() => []);

  await page.screenshot({ path: `../${screenshotName}`, fullPage: true });

  console.log(`=== ${tabName.toUpperCase()} ===`);
  console.log('URL:', page.url());
  console.log('Buttons:', JSON.stringify(buttons.slice(0, 25), null, 2));
  console.log('Selects:', JSON.stringify(selects, null, 2));
  console.log('Inputs:', JSON.stringify(inputs, null, 2));
  console.log('Alerts:', JSON.stringify(alerts, null, 2));
  console.log('Table count:', tables);
  console.log('SVG text sample:', JSON.stringify(svgText.slice(0, 30), null, 2));
  console.log('Body text sample:', bodyText.slice(0, 3500));
}

test('audit where used, recommendations, and reports tabs', async ({ page }) => {
  const logs = [];
  page.on('console', (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));

  await openPlatform(page);
  await dumpTabState(page, 'Where Used', 'tmp-where-used-audit.png');
  await dumpTabState(page, 'Recommendations', 'tmp-recommendations-audit.png');
  await dumpTabState(page, 'Reports', 'tmp-reports-audit.png');

  console.log('Console logs:', JSON.stringify(logs.slice(-50), null, 2));
});
