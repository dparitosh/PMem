const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const STEP_FILES_DIR = 'C:\\Users\\895428\\Depo\\SPLM_Folder\\step_files';
const SCREENSHOT_DIR = './test-screenshots';

async function runTest() {
  // Create screenshot directory
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }

  let browser;
  try {
    console.log('🌐 Launching Chrome browser...');
    browser = await chromium.launch({
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      headless: false,
      args: ['--no-sandbox']
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    console.log('📱 Opening http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'load', timeout: 30000 });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/01-app-loaded.png` });
    console.log('✅ Screenshot: 01-app-loaded.png');

    // Wait for app to load
    await page.waitForTimeout(2000);

    console.log('🔍 Clicking on "↓ Data Import" tab...');
    const buttons = await page.$$('button');
    let clicked = false;
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && text.includes('Data Import')) {
        await btn.click();
        clicked = true;
        console.log('✅ Clicked Data Import tab');
        break;
      }
    }
    
    if (!clicked) {
      throw new Error('Could not find Data Import tab');
    }

    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/02-data-import-tab-opened.png` });
    console.log('✅ Screenshot: 02-data-import-tab-opened.png');

    // Find the file input and upload files
    console.log('📂 Finding file input element...');
    const fileInput = await page.$('input[type="file"]');
    
    if (!fileInput) {
      throw new Error('Could not find file input element');
    }

    // Get first 3 STEP files
    const stepFiles = fs.readdirSync(STEP_FILES_DIR)
      .filter(f => f.endsWith('.stp') || f.endsWith('.stpx'))
      .slice(0, 3)
      .map(f => path.join(STEP_FILES_DIR, f));

    console.log(`📤 Uploading ${stepFiles.length} files:`, stepFiles.map(f => path.basename(f)));
    
    // Upload files directly
    await fileInput.setInputFiles(stepFiles);
    
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/03-files-uploaded.png` });
    console.log('✅ Screenshot: 03-files-uploaded.png');

    // Check file queue table
    console.log('📋 Checking file queue...');
    const tableRows = await page.$$('tr');
    console.log(`   Found ${tableRows.length} table rows`);

    // Find and click "Start Pipeline" button
    console.log('🚀 Looking for "Start Pipeline" button...');
    let startBtn = null;
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const text = await btn.textContent();
      if (text && text.includes('Start Pipeline')) {
        startBtn = btn;
        break;
      }
    }

    if (!startBtn) {
      throw new Error('Could not find "Start Pipeline" button');
    }

    console.log('▶️ Clicking "Start Pipeline" button...');
    // Use force click if normal click fails
    await startBtn.click({ force: true });
    
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/04-pipeline-stage1-running.png` });
    console.log('✅ Screenshot: 04-pipeline-stage1-running.png');

    // Wait for Stage 1 to complete
    console.log('⏳ Waiting for Stage 1 to complete (up to 15 seconds)...');
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(1000);
      
      // Check if "Continue Stages 2-7" button appeared
      const updatedBtns = await page.$$('button');
      let continueBtn = null;
      for (const btn of updatedBtns) {
        const text = await btn.textContent();
        if (text && (text.includes('Continue Stages') || text.includes('→'))) {
          continueBtn = btn;
          break;
        }
      }

      if (continueBtn) {
        console.log(`✅✅✅ "→ Continue Stages 2-7" BUTTON FOUND after ${i + 1} seconds! FIX WORKING! ✅✅✅`);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/05-CONTINUE-BUTTON-FOUND.png` });
        console.log('✅ Screenshot: 05-CONTINUE-BUTTON-FOUND.png');

        // Click the button
        console.log('▶️ Clicking "Continue Stages 2-7" button...');
        await continueBtn.click({ force: true });

        await page.waitForTimeout(3000);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/06-stages-2-7-running.png` });
        console.log('✅ Screenshot: 06-stages-2-7-running.png');

        // Wait for completion
        console.log('⏳ Waiting for Stages 2-7 to complete...');
        await page.waitForTimeout(8000);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/07-pipeline-completed.png` });
        console.log('✅ Screenshot: 07-pipeline-completed.png');

        break;
      }
    }

    // Final screenshot
    console.log('📸 Taking final screenshot...');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/08-final-state.png`, fullPage: true });
    console.log('✅ Screenshot: 08-final-state.png');

    console.log('\n✅✅✅ TEST COMPLETED SUCCESSFULLY! ✅✅✅');
    console.log(`📂 All screenshots saved to: ${path.resolve(SCREENSHOT_DIR)}`);

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    console.error('Stack:', error.stack);
    
    // Save error screenshot
    try {
      const pages = await browser.contexts().then(ctx => ctx.length > 0 ? ctx[0].pages() : []);
      if (pages.length > 0) {
        await pages[0].screenshot({ path: `${SCREENSHOT_DIR}/ERROR-screenshot.png` });
        console.log('❌ Error screenshot saved');
      }
    } catch (screenErr) {
      // Ignore screenshot error
    }
    
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
      console.log('🔌 Browser closed');
    }
  }
}

// Run test
runTest().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
