const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

async function runTest() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  const screenshotDir = './test-screenshots';
  
  // Create screenshot directory if it doesn't exist
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  try {
    console.log('📱 Opening http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: `${screenshotDir}/01-app-loaded.png` });
    console.log('✅ Screenshot: 01-app-loaded.png');

    // Wait for app to fully load
    await page.waitForTimeout(2000);

    console.log('🔍 Clicking on "↓ Data Import" tab...');
    // Click the Data Import tab
    await page.click('button:has-text("↓ Data Import")');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${screenshotDir}/02-data-import-tab-opened.png` });
    console.log('✅ Screenshot: 02-data-import-tab-opened.png');

    // Check if file upload section is visible
    console.log('📂 Looking for file upload area...');
    const uploadArea = await page.$('input[type="file"]');
    
    if (uploadArea) {
      console.log('✅ File input found');
      
      // Try to load existing files if button available
      const loadButton = await page.$('button:has-text("Add Files")')
        || await page.$('button:has-text("Load Existing")');
      
      if (loadButton) {
        console.log('🎯 Clicking "Load Existing Files" or "Add Files" button...');
        await loadButton.click();
        await page.waitForTimeout(2000);
        await page.screenshot({ path: `${screenshotDir}/03-files-loaded.png` });
        console.log('✅ Screenshot: 03-files-loaded.png');
      }
    }

    // Look for the Start Pipeline button
    console.log('🔧 Looking for "Start Pipeline" button...');
    const startButton = await page.$('button:has-text("▶ Start Pipeline")') 
      || await page.$('button:has-text("Start Pipeline")');
    
    if (startButton) {
      console.log('✅ Found Start Pipeline button. Clicking...');
      await startButton.click();
      await page.waitForTimeout(3000);
      await page.screenshot({ path: `${screenshotDir}/04-pipeline-running.png` });
      console.log('✅ Screenshot: 04-pipeline-running.png');

      // Wait for completion
      console.log('⏳ Waiting for pipeline to process...');
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `${screenshotDir}/05-pipeline-progress.png` });
      console.log('✅ Screenshot: 05-pipeline-progress.png');

      // Look for "Continue Stages 2-7" button
      console.log('🔍 Looking for "Continue Stages 2-7" button...');
      const continueButton = await page.$('button:has-text("Continue Stages")') 
        || await page.$('button:has-text("→ Continue")');
      
      if (continueButton) {
        console.log('✅ FOUND "Continue Stages 2-7" button! THIS IS THE KEY FIX!');
        await page.screenshot({ path: `${screenshotDir}/06-continue-button-visible.png` });
        console.log('✅ Screenshot: 06-continue-button-visible.png');

        console.log('▶️ Clicking "Continue Stages 2-7" button...');
        await continueButton.click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: `${screenshotDir}/07-stages-2-7-running.png` });
        console.log('✅ Screenshot: 07-stages-2-7-running.png');

        // Wait for completion
        await page.waitForTimeout(5000);
        await page.screenshot({ path: `${screenshotDir}/08-pipeline-completed.png` });
        console.log('✅ Screenshot: 08-pipeline-completed.png');
      } else {
        console.log('⚠️  "Continue Stages 2-7" button NOT FOUND');
        console.log('🔍 All buttons on page:');
        const allButtons = await page.$$('button');
        for (const btn of allButtons) {
          const text = await btn.textContent();
          console.log(`  - ${text.trim()}`);
        }
      }
    } else {
      console.log('⚠️  "Start Pipeline" button not found');
    }

    // Final comprehensive screenshot
    console.log('📸 Taking final full-page screenshot...');
    await page.screenshot({ path: `${screenshotDir}/09-final-state.png`, fullPage: true });
    console.log('✅ Screenshot: 09-final-state.png');

    console.log('\n✅ All tests completed!');
    console.log(`📂 Screenshots saved to: ${path.resolve(screenshotDir)}`);

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    await page.screenshot({ path: `${screenshotDir}/ERROR-screenshot.png` });
    console.log('❌ Error screenshot saved');
  } finally {
    await browser.close();
  }
}

runTest();
