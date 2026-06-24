const { test } = require('@playwright/test');

test('audit graph explorer after load settles', async ({ page }) => {
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  await page.setViewportSize({ width: 1600, height: 1000 });

  const openPlatform = page.getByRole('button', { name: /open platform/i });
  if (await openPlatform.count()) {
    await openPlatform.first().click();
    await page.waitForLoadState('networkidle');
  }

  const graphNav = page.getByRole('button', { name: /graph explorer/i });
  if (await graphNav.count()) {
    await graphNav.first().click();
    await page.waitForLoadState('networkidle');
  }

  await page.waitForTimeout(10000);

  console.log('loadingVisible', await page.getByText(/Loading Graph Data/i).count());
  console.log('fullGraphButtonVisible', await page.getByRole('button', { name: /full graph/i }).count());
  console.log('svgCircleCount', await page.locator('svg circle').count());
  console.log('svgTextCount', await page.locator('svg text').count());
  console.log('bodyText', (await page.locator('body').innerText()).slice(0, 2500));
});
