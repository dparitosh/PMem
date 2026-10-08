import { test, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import path from 'node:path';

const navigation = require('node:fs').readFileSync(path.resolve(__dirname, '../src/app/navigation.js'), 'utf8');
const pages = [...navigation.matchAll(/\{ id: '([^']+)', label: '([^']+)'/g)].map(([, id, label]) => ({ id, label }));
assert.equal(pages.length, 17);

for (const theme of ['light', 'dark']) {
 test(`all 17 pages navigate with retained session in ${theme} mode`, async ({ page, baseURL }, testInfo) => {
  const crashes = [], reads = [], results = [];
  page.on('pageerror', error => crashes.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && message.text().includes('ErrorBoundary caught:')) crashes.push(message.text()); });
  await page.addInitScript(theme => localStorage.setItem('depo.colorSchema', theme), theme);
  await page.addInitScript(() => {
    const ports = { qif: 8010, ontology: 8011, agentic: 8012, graph: 8013, ingestion: 8014, oslc: 8015, catalog: 8016, dataProducts: 8017, ceim: 8018, dataPipeline: 8019 };
    const roots = Object.entries(ports).map(([service, port]) => [service, `http://${location.hostname}:${port}`]).sort(([a], [b]) => a.localeCompare(b));
    sessionStorage.setItem('depo.browserSession.v1', JSON.stringify({ token: 'depo_session_navigation', deadline: Date.now() + 600000, profiles: ['GRAPH_READ_TOKEN'], scope: JSON.stringify(['', roots]) }));
    window.__navigationDocument = Math.random();
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === new URL(baseURL).origin || !['http:', 'https:'].includes(url.protocol)) return route.continue();
    if (route.request().method() !== 'OPTIONS') reads.push({ path: url.pathname, method: route.request().method(), authorization: route.request().headers().authorization || '' });
    let body = { status: 'success', ontologies: [], products: [], nodes: [], links: [], tools: [], agents: [], services: [], workflows: [], runs: [], jobs: [], assets: [], requirements: [], sources: [], items: [], mappings: [], count: 0, total: 0, next_offset: null, data: { runs: [], jobs: [], nodes: [], links: [], assets: [] } };
    if (url.pathname.includes('health') || url.pathname.includes('ready')) body.status = 'ok';
    if (url.pathname === '/auth/access') body = { status: 'authorized' };
    if (url.pathname.endsWith('/graph/metrics')) body = { scope: { sampled: false, type: 'published_rdf_projection', ontology_id: '' }, counts: {} };
    if (url.pathname.endsWith('/graph/overview')) body = { nodes: [{ elementId: 'navigation-fixture-node', labels: ['OntologyClass'], properties: { name: 'Navigation fixture' } }], relationships: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' }, body: JSON.stringify(body) });
  });
  await page.goto('/#/graph');
  await page.getByRole('button', {name:'Revalidate or reconnect API access',exact:true}).click();
  await page.getByText(/Read access verified:/).waitFor();
  const documentIdentity = await page.evaluate(() => window.__navigationDocument);
  for (const { id, label } of pages) {
    const item = page.locator('ix-menu-item').nth(pages.findIndex(item => item.id === id));
    await item.click();
    await page.waitForFunction(label => document.querySelector('ix-content-header')?.headerTitle === label, label);
    await page.waitForFunction(() => !document.querySelector('.depo-page-loading'));
    if (id === 'graph') await page.locator('.node-circle').first().waitFor();
    assert.equal(await page.evaluate(() => window.__navigationDocument), documentIdentity, 'Navigation must not reload the document');
    assert.equal(await page.getByText('Warning: Something went wrong', { exact: true }).count(), 0, `No error boundary on ${label}: ${crashes.join('; ')}`);
    results.push({ id, label, status: 'passed' });
    if (id === 'admin') {
      await page.getByRole('tab', {name:'Agents & workflows', exact:true}).click();
      await page.locator('.depo-agent-recommendations').screenshot({ path: testInfo.outputPath(`recommendations-${theme}-desktop.png`) });
      await page.getByRole('tab', {name:'API access', exact:true}).click();
      assert.equal(await page.getByLabel('Administrator key for connection', {exact:true}).isVisible(), true);
      await page.getByRole('tab', {name:'Overview', exact:true}).click();
    }
    if (id === 'ontology') {
      await page.getByRole('tab', { name: '2. Semantic Bridge', exact: true }).click();
      await page.locator('.depo-bridge-review').waitFor();
      assert.equal(await page.locator('.depo-ontology-merge').getAttribute('open'), null);
      await page.locator('.depo-bridge-review').screenshot({ path: testInfo.outputPath(`bridge-${theme}-desktop.png`) });
    }
  }
  await page.goBack();
  await page.goForward();
  await page.setViewportSize({ width: 390, height: 800 });
  for (const { id, label } of pages) {
    await page.evaluate(id => { location.hash = '#/' + id; }, id);
    await page.waitForFunction(label => document.querySelector('ix-content-header')?.headerTitle === label, label);
    await page.waitForFunction(() => !document.querySelector('.depo-page-loading'));
    assert.equal(await page.getByText('Warning: Something went wrong', { exact: true }).count(), 0, `No narrow-page error boundary on ${label}`);
    if (id === 'admin') {
      await page.getByRole('tab', {name:'Agents & workflows', exact:true}).click();
      await page.locator('.depo-agent-recommendations').screenshot({ path: testInfo.outputPath(`recommendations-${theme}-mobile.png`) });
    }
  }
  assert.deepEqual(crashes, []);
  const protectedReads = reads.filter(read => /\/api\/v1\/(?:catalog\/products|data-products|observability\/summary|graph\/metrics)$/.test(read.path));
  assert.ok(protectedReads.length > 0);
  assert.ok(protectedReads.every(read => read.authorization === 'Bearer depo_session_navigation'), 'Read session follows protected requests across page navigation');
  await page.setViewportSize({width:1280,height:800});
  await page.evaluate(async () => {
    const auth = await import('/src/services/serviceAuth.js');
    auth.expireBrowserSession('depo_session_navigation');
  });
  await page.getByText('API session expired. Use Reconnect access to restore registered scopes.').waitFor();
  await page.getByRole('button', {name:'Revalidate or reconnect API access',exact:true}).click();
  await page.getByRole('tab', {name:'API access',exact:true}).waitFor();
  await expect(page.getByRole('tab', {name:'API access',exact:true})).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByLabel('Administrator key for connection', {exact:true})).toBeVisible();
 });
}
