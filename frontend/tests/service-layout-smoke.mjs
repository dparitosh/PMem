import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.addInitScript(() => {
    const services = { qif: 8010, ontology: 8011, agentic: 8012, graph: 8013, ingestion: 8014, oslc: 8015, catalog: 8016, dataProducts: 8017, ceim: 8018, dataPipeline: 8019 };
    const roots = Object.entries(services).map(([name, port]) => [name, `http://127.0.0.1:${port}`]).sort(([a], [b]) => a.localeCompare(b));
    sessionStorage.setItem('depo.browserSession.v1', JSON.stringify({ token: 'depo_session_layout_fixture', profiles: ['GRAPH_READ_TOKEN'], deadline: Date.now() + 600000, scope: JSON.stringify(['', roots]) }));
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.port === '4173' || url.protocol !== 'http:') return route.continue();
    let body = { status: 'success', ontologies: [], products: [], nodes: [], links: [], tools: [], agents: [], services: [], workflows: [] };
    if (url.pathname === '/auth/access') body = { status: 'authorized' };
    if (url.pathname.endsWith('/oslc/health')) body = { status: 'ok', server: 'enabled', remote_configured: false };
    if (url.pathname.endsWith('/catalog/products') || url.pathname.endsWith('/data-products')) body = { products: [], count: 100, total: 250, next_offset: null };
    if (url.pathname.endsWith('/llm/health')) body = { status: 'connection_failed', model: 'llama3', endpoint: 'http://127.0.0.1:11434/api/tags', probe_timeout_seconds: 5, action: 'Start Ollama on the application VM.', ontology_agent_enabled: true, companion_enabled: true };
    if (url.pathname.endsWith('/workflow-runs/run-layout')) body = { status: 'failed', pending_step: { mutates: true }, reconciliation_required: true, traces: [], deadline_at: new Date(Date.now() + 600000).toISOString() };
    await route.fulfill({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*' }, body: JSON.stringify(body) });
  });
  await page.goto('http://127.0.0.1:4173/#/admin');
  const integrations = page.getByRole('region', { name: 'Platform service integrations' });
  await integrations.waitFor();
  await page.getByText('250', { exact: true }).first().waitFor();
  await page.getByText('Check offline Ollama', { exact: true }).click();
  await page.getByText('connection_failed', { exact: true }).waitFor();
  await page.getByLabel('Workflow run ID').fill('run-layout');
  await page.getByText('Inspect / refresh', { exact: true }).click();
  await page.getByLabel('Downstream verification evidence').waitFor();
  await mkdir('../deliverables/service-layout-review', { recursive: true });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `../deliverables/service-layout-review/admin-${width}.png`, fullPage: true });
    await integrations.screenshot({ path: `../deliverables/service-layout-review/integrations-${width}.png` });
    const cards = await page.locator('.depo-service-card').evaluateAll(cards => cards.map(card => {
      const box = card.getBoundingClientRect();
      return [...card.querySelectorAll('.depo-card-detail, ix-button')].every(child => {
        const bounds = child.getBoundingClientRect();
        return bounds.top >= box.top && bounds.bottom <= box.bottom && bounds.left >= box.left && bounds.right <= box.right;
      });
    }));
    assert.equal(cards.length, 3);
    assert.ok(cards.every(Boolean), `Card content must fit at ${width}px`);
    const padding = await page.locator('[aria-label="Agent workflow controls"] .depo-panel__body').evaluate(el => getComputedStyle(el).padding);
    assert.notEqual(padding, '0px');
    const reconciliationFits = await page.locator('.depo-workflow-reconciliation').evaluate(element => {
      const box = element.getBoundingClientRect();
      return [...element.querySelectorAll('textarea, ix-button')].every(child => {
        const bounds = child.getBoundingClientRect();
        return bounds.left >= box.left - 1 && bounds.right <= box.right + 1;
      });
    });
    assert.ok(reconciliationFits, `Workflow receipt fields must fit at ${width}px`);
  }
  console.log('PASS: integration rows and refresh button fit at desktop/mobile widths; totals and Ollama diagnostics render.');
} finally { await browser.close(); }
