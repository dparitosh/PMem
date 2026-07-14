const { test, expect } = require('@playwright/test');

test('all DEPO pages remain navigable at desktop and narrow viewport', async ({ page }) => {
  await page.route('http://localhost:8000/**', async (route) => {
    const url = route.request().url();
    const body = url.endsWith('/health')
      ? { status: 'healthy' }
      : { status: 'success', ontologies: [], nodes: [], links: [], requirements: [], assets: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.addInitScript(() => localStorage.setItem('depo.activePage', 'graph'));
  await page.goto('/', { waitUntil: 'networkidle' });

  const pages = ['Import', 'Ontology Junction', 'Metadata Registry', 'Graph Explorer', 'Modeling', 'ReqIF', 'Where Used', 'Recommendations', 'Reports', 'Admin'];
  for (const name of pages) {
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  }

  await page.setViewportSize({ width: 390, height: 700 });
  await expect(page.getByRole('navigation', { name: 'Application navigation' })).toBeVisible();
  await page.getByRole('button', { name: 'Graph Explorer', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Graph Explorer', exact: true })).toBeVisible();
});
