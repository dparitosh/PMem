const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const STEP_FILES_DIR = 'C:\\Users\\895428\\Depo\\SPLM_Folder\\step_files';
const SCREENSHOT_DIR = './test-screenshots-v2';

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
    
    // Set viewport for consistent screenshots
    await page.setViewportSize({ width: 1400, height: 900 });

    console.log('📱 Opening http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'load', timeout: 30000 });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/01-app-loaded.png` });
    console.log('✅ Screenshot: 01-app-loaded.png');

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
    
    if (!clicked) throw new Error('Could not find Data Import tab');

    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/02-data-import-tab-opened.png` });
    console.log('✅ Screenshot: 02-data-import-tab-opened.png');

    // Find and use file input
    console.log('📂 Finding file input element...');
    const fileInput = await page.$('input[type="file"]');
    if (!fileInput) throw new Error('Could not find file input element');

    // Upload 2 small files
    const stepFiles = fs.readdirSync(STEP_FILES_DIR)
      .filter(f => f.endsWith('.stp') || f.endsWith('.stpx'))
      .slice(0, 2)
      .map(f => path.join(STEP_FILES_DIR, f));

    console.log(`📤 Uploading ${stepFiles.length} files:`, stepFiles.map(f => path.basename(f)));
    await fileInput.setInputFiles(stepFiles);
    
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/03-files-uploaded.png` });
    console.log('✅ Screenshot: 03-files-uploaded.png');

    // Find "Start Pipeline" or "+ Start" button
    console.log('🚀 Looking for "Start Pipeline" button...');
    let startBtn = null;
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const text = await btn.textContent();
      if (text && (text.includes('Start Pipeline') || text.includes('▶ Start'))) {
        startBtn = btn;
        console.log(`   Found button: "${text.trim()}"`);
        break;
      }
    }

    if (!startBtn) {
      console.log('   Available buttons:');
      for (const btn of allBtns) {
        const text = await btn.textContent();
        if (text && text.trim()) {
          console.log(`   - "${text.trim()}"`);
        }
      }
      throw new Error('Could not find Start Pipeline button');
    }

    console.log('▶️ Clicking "Start Pipeline" button...');
    await startBtn.click({ force: true });
    
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/04-pipeline-processing.png` });
    console.log('✅ Screenshot: 04-pipeline-processing.png');

    // Wait up to 30 seconds for "Commit" button to appear (when verify stage is reached)
    console.log('⏳ Waiting for pipeline to reach "verify" stage and show Commit button...');
    let commitBtn = null;
    let foundAt = -1;
    
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(1000);
      
      const updatedBtns = await page.$$('button');
      for (const btn of updatedBtns) {
        const text = await btn.textContent();
        if (text && (text.includes('Commit') || text.includes('✓ Commit'))) {
          commitBtn = btn;
          foundAt = i + 1;
          break;
        }
      }

      if (commitBtn) {
        console.log(`✅✅✅ "✓ Commit" BUTTON FOUND after ${foundAt} seconds! VERIFY STAGE REACHED! ✅✅✅`);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/05-commit-button-visible.png` });
        console.log('✅ Screenshot: 05-commit-button-visible.png');

        // Show current button states
        console.log('\n📋 Current button states:');
        for (const btn of updatedBtns) {
          const text = await btn.textContent();
          if (text && text.trim() && text.length < 50) {
            console.log(`   - "${text.trim()}"`);
          }
        }

        // Click Commit button
        console.log('\n💾 Clicking "Commit" button to finalize import...');
        await commitBtn.click({ force: true });

        await page.waitForTimeout(2000);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/06-after-commit.png` });
        console.log('✅ Screenshot: 06-after-commit.png');

        break;
      }

      if (i === 5 || i === 15 || i === 29) {
        console.log(`   ... still waiting (${i + 1}s elapsed)`);
        
        // Show what buttons are visible
        const currentBtns = await page.$$('button');
        const btnTexts = [];
        for (const btn of currentBtns) {
          const text = await btn.textContent();
          if (text && text.trim() && (text.includes('Commit') || text.includes('Start') || text.includes('Process'))) {
            btnTexts.push(text.trim().substring(0, 40));
          }
        }
        if (btnTexts.length > 0) {
          console.log(`   Buttons: ${btnTexts.join(', ')}`);
        }
      }
    }

    if (!commitBtn) {
      console.log('⚠️ "Commit" button not found after 30 seconds');
      console.log('   Taking screenshot of current state...');
    }

    // Final screenshot
    console.log('\n📸 Taking final full-page screenshot...');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/07-final-state.png`, fullPage: true });
    console.log('✅ Screenshot: 07-final-state.png');

    if (foundAt > 0) {
      console.log(`\n✅✅✅ TEST PASSED! Commit button appeared after ${foundAt}s! ✅✅✅`);
    } else {
      console.log('\n⚠️ Test completed but Commit button not found - check screenshots');
    }
    
    console.log(`📂 All screenshots saved to: ${path.resolve(SCREENSHOT_DIR)}`);

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
      console.log('\n🔌 Browser closed');
    }
  }
}

runTest().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
