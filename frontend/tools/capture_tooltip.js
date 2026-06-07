const { chromium, request } = require('playwright');
const fs = require('fs');
const path = require('path');

async function launchChromiumWithFallback() {
  try {
    const b = await chromium.launch({ headless: true });
    console.log('Launched playwright-managed chromium');
    return b;
  } catch (err) {
    console.warn('Default playwright chromium launch failed:', err.message);
    // Try common local chrome/chromium paths (Windows)
    const candidates = [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
    ];
    for (const p of candidates) {
      try {
        if (fs.existsSync(p)) {
          console.log('Attempting to launch local executable at', p);
          const b2 = await chromium.launch({ headless: true, executablePath: p });
          console.log('Launched local browser at', p);
          return b2;
        }
      } catch (e2) {
        // continue
      }
    }
    throw err;
  }
}

(async () => {
  const browser = await launchChromiumWithFallback();
  const page = await browser.newPage();
  const envUrl = process.env.URL;
  const defaultHosts = ['http://127.0.0.1:3000/', 'http://localhost:3000/'];
  // include LAN IP if available
  const lan = process.env.LAN_IP || 'http://192.168.1.9:3000/';
  const urls = envUrl ? [envUrl, ...defaultHosts, lan] : [...defaultHosts, lan];
  console.log('Trying URLs:', urls.join(' '));
  const consoleMessages = [];
  page.on('console', msg => {
    try { consoleMessages.push(`${msg.type()}: ${msg.text()}`); } catch (e) {}
  });
  const pageErrors = [];
  page.on('pageerror', err => { pageErrors.push(String(err)); });
  try {
    // Retry navigation to handle transient connection refusals
    let navigated = false;
    for (const u of urls) {
      for (let attempt = 1; attempt <= 5; attempt++) {
        try {
          console.log(`Navigating to ${u} (attempt ${attempt})`);
          await page.goto(u, { waitUntil: 'networkidle', timeout: 60000 });
          navigated = true;
          break;
        } catch (e) {
          console.warn(`Navigation attempt ${attempt} to ${u} failed: ${e.message}`);
          await new Promise(r => setTimeout(r, 2000));
        }
      }
      if (navigated) break;
    }
    if (!navigated) throw new Error('Could not navigate to any frontend URL');
      // Ensure Data Import tab is open so the import UI (and ontology dropdown) is rendered
      try {
        // Try multiple strategies to open the ingestion / Data Import tab
        let clicked = false;
        const byText = page.locator('button:has-text("Data Import")');
        if (await byText.count() > 0) {
          await byText.first().click(); clicked = true;
        }
        if (!clicked) {
          const byLabel = page.locator('button:has-text("↓ Data Import")');
          if (await byLabel.count() > 0) { await byLabel.first().click(); clicked = true; }
        }
        if (!clicked) {
          // Fallback: click the 3rd button in the tab nav bar if present
          const tabBtns = page.locator('.tab-nav-bar button');
          if (await tabBtns.count() >= 3) { await tabBtns.nth(2).click(); clicked = true; }
        }
        if (clicked) { console.log('Opened Data Import tab'); await page.waitForTimeout(800); }
      } catch (e) {
        // ignore if not present
      }

    // Instead of attempted automatic uploads, capture registry info and page state safely
    try {
      const backendBase = process.env.BACKEND || 'http://localhost:8000';
      const req = await request.newContext({ baseURL: backendBase });
      console.log('Checking registered ontologies at', backendBase + '/api/v1/ontology/registered');
      const regRes = await req.get('/api/v1/ontology/registered');
      if (regRes.ok()) {
        const regJson = await regRes.json().catch(() => null);
        const list = regJson?.ontologies || regJson?.items || (Array.isArray(regJson) ? regJson : []);
        console.log('Registered ontologies count:', Array.isArray(list) ? list.length : 'unknown');
      } else {
        console.warn('Could not query registered ontologies:', regRes.status());
      }
      await req.dispose();
      // Wait for SPA render then capture full page and select lists
      await page.waitForTimeout(3000);
      try {
        const screenshotPath = path.resolve(__dirname, '..', '..', 'frontend_screenshot.png');
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log('Saved screenshot to', screenshotPath);

        const selects = await page.evaluate(() => {
          return Array.from(document.querySelectorAll('select')).map(s => ({
            id: s.id || null,
            title: s.title || null,
            options: Array.from(s.options).map(o => ({ value: o.value, text: o.textContent.trim() }))
          }));
        });
        const optsPath = path.resolve(__dirname, '..', '..', 'frontend_selects.json');
        fs.writeFileSync(optsPath, JSON.stringify(selects, null, 2));
        console.log('Saved select options to', optsPath);
      } catch (capErr) {
        console.warn('Capture failed:', capErr.message || capErr);
      }
      // Done with safe capture; close browser and exit
      await browser.close();
      process.exit(0);
    } catch (e) {
      console.warn('Registry check failed:', e.message || e);
    }

    // Try opening the Graph Explorer panel if present (makes nodes visible)
    try {
      const ge = page.locator('button:has-text("Graph Explorer")');
      if (await ge.count() > 0) {
        console.log('Clicking Graph Explorer button to reveal graph');
        await ge.first().click({ timeout: 5000 });
        // allow UI to update
        await page.waitForTimeout(1000);
      }
    } catch (e) {
      console.warn('Graph Explorer button not present or click failed:', e.message);
    }

    // try several possible node selectors used in different layers
    const possibleNodeSelectors = ['.node-group', '.instance-node', '.schema-node', '.node', 'circle'];
    let nodeSelector = null;
    // Allow more time for dynamic data and rendering (total ~60s across attempts)
    for (const sel of possibleNodeSelectors) {
      try {
        await page.waitForSelector(sel, { timeout: 30000 });
        nodeSelector = sel;
        console.log('Found node selector:', sel);
        break;
      } catch (e) {
        // try next
      }
    }
    if (!nodeSelector) {
      throw new Error('No recognized node selector found on the page');
    }

    // proceed with node interactions below (click, tooltip, screenshot)
    // Click the first node by computing its center
    const nodeHandle = await page.$(nodeSelector);
    if (!nodeHandle) {
      throw new Error('No node handle after selector found');
    }

    const box = await nodeHandle.boundingBox();
    if (!box) {
      throw new Error('Could not get bounding box for node');
    }

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.click(cx, cy);

    // Wait for tooltip to appear
    const tooltip = await page.waitForSelector('.tooltip', { timeout: 5000 });
    if (!tooltip) {
      throw new Error('Tooltip not found');
    }

    // Ensure it's visible
    await page.waitForFunction(() => {
      const t = document.querySelector('.tooltip');
      return t && window.getComputedStyle(t).opacity !== '0' && window.getComputedStyle(t).display !== 'none';
    }, { timeout: 5000 });

    // Take screenshot of the tooltip element
    const screenshotPath = 'tooltip_screenshot.png';
    await tooltip.screenshot({ path: screenshotPath });
    console.log('Saved tooltip screenshot to', screenshotPath);

  } catch (err) {
    console.error('Capture failed:', err.message);
    try {
      const html = await page.content();
      fs.writeFileSync('capture_page.html', html, { encoding: 'utf8' });
      console.log('Wrote capture_page.html for debugging');
    } catch (werr) {
      console.error('Failed to write page content:', werr.message);
    }
    try { fs.writeFileSync('capture_console.log', consoleMessages.join('\n'), {encoding:'utf8'}); } catch (e) {}
    try { fs.writeFileSync('capture_page_errors.log', pageErrors.join('\n'), {encoding:'utf8'}); } catch (e) {}
    await browser.close();
    process.exit(6);
  }

  await browser.close();
})();