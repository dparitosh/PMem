import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const navigation = await readFile(new URL('../src/app/navigation.js', import.meta.url), 'utf8');
const pages = [...navigation.matchAll(/\{ id: '([^']+)', label: '([^']+)'/g)].map(([, id, label]) => ({ id, label }));
assert.equal(pages.length, 17);
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const crashes = [];
const reads = [];
const results = [];
page.on('pageerror', error => crashes.push(error.message));
page.on('console', message => { if (message.type() === 'error' && message.text().includes('ErrorBoundary caught:')) crashes.push(message.text()); });
try {
  await page.addInitScript(() => {
    const ports = { qif: 8010, ontology: 8011, agentic: 8012, graph: 8013, ingestion: 8014, oslc: 8015, catalog: 8016, dataProducts: 8017, ceim: 8018, dataPipeline: 8019 };
    const roots = Object.entries(ports).map(([service, port]) => [service, `http://127.0.0.1:${port}`]).sort(([a], [b]) => a.localeCompare(b));
    sessionStorage.setItem('depo.browserSession.v1', JSON.stringify({ token: 'depo_session_navigation', deadline: Date.now() + 600000, profiles: ['GRAPH_READ_TOKEN'], scope: JSON.stringify(['', roots]) }));
    localStorage.setItem('depo.colorSchema', 'dark'); window.__navigationDocument = Math.random();
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.port === '4173' || url.protocol !== 'http:') return route.continue();
    if (route.request().method() !== 'OPTIONS') reads.push({ path: url.pathname, method: route.request().method(), authorization: route.request().headers().authorization || '' });
    let body = { status: 'success', ontologies: [], products: [], nodes: [], links: [], tools: [], agents: [], services: [], workflows: [], runs: [], jobs: [], assets: [], requirements: [], sources: [], items: [], mappings: [], count: 0, total: 0, next_offset: null, data: { runs: [], jobs: [], nodes: [], links: [], assets: [] } };
    if (url.pathname.includes('health') || url.pathname.includes('ready')) body.status = 'ok';
    if (url.pathname === '/auth/access') body = { status: 'authorized' };
    if (url.pathname.endsWith('/graph/metrics')) body = { scope: { sampled: false, type: 'published_rdf_projection', ontology_id: '' }, counts: {} };
    if (url.pathname.endsWith('/graph/overview')) body = { nodes: [{ elementId: 'navigation-fixture-node', labels: ['OntologyClass'], properties: { name: 'Navigation fixture' } }], relationships: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' }, body: JSON.stringify(body) });
  });
  await page.goto('http://127.0.0.1:4173/#/graph');
  const documentIdentity = await page.evaluate(() => window.__navigationDocument);
  async function checkCollapsedAdmin() {
    await page.locator('ix-menu').evaluate(menu => { menu.expand = false; });
    const admin = page.locator('ix-menu-item').filter({ hasText: 'Admin' });
    await admin.scrollIntoViewIfNeeded();
    await admin.click({ trial: true });
    assert.equal(await page.locator('ix-menu').evaluate(menu => menu.enableToggleTheme), false);
  }
  await checkCollapsedAdmin();
  assert.equal(await page.locator('ix-menu').evaluate(el => el.enableToggleTheme), false);
  assert.equal(await page.locator('html').getAttribute('data-ix-color-schema'), 'dark');

  for (const { id, label } of pages) {
    const item = page.locator('ix-menu-item').nth(pages.findIndex(item => item.id === id));
    await item.click();
    await page.waitForFunction(label => document.querySelector('ix-content-header')?.headerTitle === label, label);
    await page.waitForFunction(() => !document.querySelector('.depo-page-loading'));
    if (id === 'graph') await page.locator('.node-circle').first().waitFor();
    assert.equal(await page.evaluate(() => window.__navigationDocument), documentIdentity, 'Navigation must not reload the document');
    assert.equal(await page.getByText('Warning: Something went wrong', { exact: true }).count(), 0, `No error boundary on ${label}: ${crashes.join('; ')}`);
    assert.equal(await page.locator('.depo-ix-page__body').evaluate(el => getComputedStyle(el).color), 'rgb(241, 245, 249)');
    if (id === 'admin') {
      const contrast = await page.locator('details > summary').evaluateAll(elements => {
        const luminance = value => value.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => {
          const n = v / 255;
          return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4;
        }).reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0);
        return elements.filter(el => el.getBoundingClientRect().height > 0).map(el => {
          let parent = el;
          while (parent && getComputedStyle(parent).backgroundColor === 'rgba(0, 0, 0, 0)') parent = parent.parentElement;
          const a = luminance(getComputedStyle(el).color);
          const b = luminance(getComputedStyle(parent).backgroundColor);
          return { text: el.textContent.trim().slice(0, 80), ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
        });
      });
      assert.ok(contrast.length, 'Admin summaries must be present');
      assert.deepEqual(contrast.filter(item => item.ratio < 4.5), [], 'Admin summary text must meet 4.5:1 contrast');
    }
    results.push({ id, label, status: 'passed' });
  }
  await page.goBack();
  await page.goForward();
  await page.setViewportSize({ width: 1440, height: 600 });
  await checkCollapsedAdmin();
  await page.setViewportSize({ width: 390, height: 800 });
  for (const { id, label } of pages) {
    await page.evaluate(id => { location.hash = '#/' + id; }, id);
    await page.waitForFunction(label => document.querySelector('ix-content-header')?.headerTitle === label, label);
    await page.waitForFunction(() => !document.querySelector('.depo-page-loading'));
    assert.equal(await page.getByText('Warning: Something went wrong', { exact: true }).count(), 0, `No narrow-page error boundary on ${label}`);
  }
  assert.deepEqual(crashes, []);
  const protectedReads = reads.filter(read => /\/api\/v1\/(?:catalog\/products|data-products|observability\/summary|graph\/metrics)$/.test(read.path));
  assert.ok(protectedReads.length > 0);
  assert.ok(protectedReads.every(read => read.authorization === 'Bearer depo_session_navigation'), 'Read session follows protected requests across page navigation');
  await writeFile('../deliverables/dark-pages-navigation-results.json', JSON.stringify({ mode: 'mocked service responses, real Chromium', viewports: [1440, 390], pages: results, protectedReadRequests: protectedReads.length, crashes }, null, 2));
  console.log(`PASS: ${results.length} menu pages; desktop clicks, narrow hash routes, browser history, unchanged document and session headers; no JavaScript crashes.`);
} finally { await browser.close(); }
