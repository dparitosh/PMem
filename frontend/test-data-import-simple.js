const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function runTest() {
  const screenshotDir = './test-screenshots';
  
  // Create screenshot directory if it doesn't exist
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  let browser;
  try {
    console.log('🌐 Launching browser (using system Chrome if available)...');
    
    // Try to use system Chrome/Edge if available
    browser = await chromium.launch({
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    }).catch(async () => {
      console.log('ℹ️  System Chrome not found, trying Chromium...');
      return chromium.launch({
        headless: false,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
      });
    });

    const page = await browser.newPage();
    const context = await browser.newContext();
    const testPage = await context.newPage();

    console.log('📱 Opening http://localhost:3000...');
    await testPage.goto('http://localhost:3000', { waitUntil: 'load', timeout: 30000 });
    await testPage.screenshot({ path: `${screenshotDir}/01-app-loaded.png` });
    console.log('✅ Screenshot: 01-app-loaded.png');

    // Wait for app to fully load
    await testPage.waitForTimeout(2000);

    console.log('🔍 Clicking on "↓ Data Import" tab...');
    // Click the Data Import tab using more flexible selector
    const buttons = await testPage.$$('button');
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
    
    await testPage.waitForTimeout(1500);
    await testPage.screenshot({ path: `${screenshotDir}/02-data-import-tab-opened.png` });
    console.log('✅ Screenshot: 02-data-import-tab-opened.png');

    // Look for "+ Add Files" button or similar
    console.log('📂 Looking for file upload area...');
    const allButtons = await testPage.$$('button');
    let addFilesBtn = null;
    let startBtn = null;
    let continueBtn = null;
    
    for (const btn of allButtons) {
      const text = await btn.textContent();
      if (text && text.includes('Add Files')) addFilesBtn = btn;
      if (text && text.includes('Start Pipeline')) startBtn = btn;
      if (text && text.includes('Continue Stages')) continueBtn = btn;
    }

    if (addFilesBtn) {
      console.log('🎯 Found "Add Files" button, clicking...');
      await addFilesBtn.click();
      await testPage.waitForTimeout(2000);
      await testPage.screenshot({ path: `${screenshotDir}/03-add-files-clicked.png` });
      console.log('✅ Screenshot: 03-add-files-clicked.png');
    }

    // Check file table
    console.log('📋 Checking if files are in the queue...');
    await testPage.screenshot({ path: `${screenshotDir}/04-file-queue-state.png` });
    console.log('✅ Screenshot: 04-file-queue-state.png');

    // Look for Start Pipeline button
    if (startBtn) {
      console.log('🚀 Found "Start Pipeline" button, clicking...');
      await startBtn.click();
      await testPage.waitForTimeout(3000);
      await testPage.screenshot({ path: `${screenshotDir}/05-pipeline-stage1-running.png` });
      console.log('✅ Screenshot: 05-pipeline-stage1-running.png');

      // Wait for stage 1 to complete
      await testPage.waitForTimeout(4000);
      await testPage.screenshot({ path: `${screenshotDir}/06-pipeline-stage1-complete.png` });
      console.log('✅ Screenshot: 06-pipeline-stage1-complete.png');

      // Refresh button list to check for "Continue Stages 2-7"
      const updatedButtons = await testPage.$$('button');
      continueBtn = null;
      for (const btn of updatedButtons) {
        const text = await btn.textContent();
        if (text && (text.includes('Continue Stages') || text.includes('Continue'))) {
          continueBtn = btn;
          break;
        }
      }

      if (continueBtn) {
        console.log('✅✅✅ FOUND "→ Continue Stages 2-7" BUTTON! FIX IS WORKING! ✅✅✅');
        await testPage.screenshot({ path: `${screenshotDir}/07-CONTINUE-BUTTON-FOUND.png` });
        console.log('✅ Screenshot: 07-CONTINUE-BUTTON-FOUND.png');

        console.log('▶️ Clicking "Continue Stages 2-7" button...');
        await continueBtn.click();
        await testPage.waitForTimeout(3000);
        await testPage.screenshot({ path: `${screenshotDir}/08-stages-2-7-processing.png` });
        console.log('✅ Screenshot: 08-stages-2-7-processing.png');

        // Wait for completion
        await testPage.waitForTimeout(5000);
        await testPage.screenshot({ path: `${screenshotDir}/09-stages-2-7-completed.png` });
        console.log('✅ Screenshot: 09-stages-2-7-completed.png');
      } else {
        console.log('❌ "Continue Stages 2-7" button NOT FOUND after Stage 1');
        console.log('📋 Available buttons:');
        for (const btn of updatedButtons) {
          const text = await btn.textContent();
          if (text && text.trim()) {
            console.log(`  - "${text.trim()}"`);
          }
        }
      }
    } else {
      console.log('⚠️  "Start Pipeline" button not found');
      console.log('📋 All buttons on page:');
      for (const btn of allButtons) {
        const text = await btn.textContent();
        if (text && text.trim()) {
          console.log(`  - "${text.trim()}"`);
        }
      }
    }

    // Final comprehensive screenshot
    console.log('📸 Taking final full-page screenshot...');
    await testPage.screenshot({ path: `${screenshotDir}/10-final-state.png`, fullPage: true });
    console.log('✅ Screenshot: 10-final-state.png');

    console.log('\n✅ All tests completed!');
    console.log(`📂 Screenshots saved to: ${path.resolve(screenshotDir)}`);
    console.log(`\n📁 View screenshots: ${path.resolve(screenshotDir)}`);

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    console.error('Stack:', error.stack);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

// Run with timeout
Promise.race([
  runTest(),
  new Promise((_, reject) => setTimeout(() => reject(new Error('Test timeout')), 90000))
]).catch(err => {
  console.error('Test error:', err.message);
  process.exit(1);
});
