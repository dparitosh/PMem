const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const STEP_FILES_DIR = 'C:\\Users\\895428\\Depo\\SPLM_Folder\\step_files';
const SCREENSHOT_DIR = './test-stage-transitions';

async function runTest() {
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
    await page.setViewportSize({ width: 1400, height: 900 });

    console.log('📱 Opening http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'load', timeout: 30000 });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/00-initial.png` });
    console.log('✅ Screenshot: 00-initial.png');

    await page.waitForTimeout(2000);

    console.log('\n🔍 Clicking on "↓ Data Import" tab...');
    const buttons = await page.$$('button');
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && text.includes('Data Import')) {
        await btn.click();
        break;
      }
    }

    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/01-import-tab.png` });
    console.log('✅ Screenshot: 01-import-tab.png');

    // Upload 1 small file
    console.log('\n📂 Uploading 1 STEP file...');
    const fileInput = await page.$('input[type="file"]');
    const stepFiles = fs.readdirSync(STEP_FILES_DIR)
      .filter(f => f.endsWith('.stp'))
      .slice(0, 1)
      .map(f => path.join(STEP_FILES_DIR, f));

    console.log(`   File: ${path.basename(stepFiles[0])}`);
    await fileInput.setInputFiles(stepFiles);
    
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/02-file-added.png` });
    console.log('✅ Screenshot: 02-file-added.png');

    // Click Start Pipeline
    console.log('\n▶️ Clicking "▶ Start Pipeline" button...');
    let startBtn = null;
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const text = await btn.textContent();
      if (text && text.includes('Start Pipeline')) {
        startBtn = btn;
        break;
      }
    }
    await startBtn.click({ force: true });
    
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/03-start-clicked.png` });
    console.log('✅ Screenshot: 03-start-clicked.png');

    // Monitor stage transitions
    console.log('\n⏳ Monitoring pipeline stages...');
    console.log('   Polling backend /data-import/status endpoint every 500ms\n');
    
    let lastStage = null;
    let stageTransitions = [];
    let taskId = null;

    // Get task ID from backend
    await page.waitForTimeout(500);
    const tasksResponse = await page.evaluate(() => 
      fetch('http://localhost:8000/data-import/tasks')
        .then(r => r.json())
    );
    
    if (tasksResponse.tasks && tasksResponse.tasks.length > 0) {
      taskId = tasksResponse.tasks[0].task_id;
      console.log(`   Task ID: ${taskId}`);
    }

    // Poll for stage transitions
    let captureCount = 4;
    for (let poll = 0; poll < 60; poll++) {
      await page.waitForTimeout(500);

      // Fetch status from backend
      const statusResponse = await page.evaluate((tid) => 
        fetch(`http://localhost:8000/data-import/status/${tid}`)
          .then(r => r.json())
      , taskId);

      if (statusResponse && statusResponse.current_stage) {
        const stage = statusResponse.current_stage;
        const progress = statusResponse.progress;
        const status = statusResponse.status;

        // Log stage changes
        if (stage !== lastStage) {
          console.log(`   ✨ Stage transition: ${lastStage} → ${stage} (${progress}%)`);
          stageTransitions.push({
            from: lastStage,
            to: stage,
            progress: progress,
            time: poll * 500
          });

          // Capture screenshot at transition
          await page.screenshot({ path: `${SCREENSHOT_DIR}/${String(captureCount).padStart(2, '0')}-stage-${stage}.png` });
          console.log(`      Screenshot: ${String(captureCount).padStart(2, '0')}-stage-${stage}.png`);
          captureCount++;

          lastStage = stage;
        }

        // Stop when completed
        if (status === 'completed') {
          console.log(`\n✅ Pipeline completed (${progress}%)`);
          break;
        }
      }

      // Timeout after 30 seconds
      if (poll >= 60) {
        console.log('\n⏱️ Timeout after 30 seconds');
        break;
      }
    }

    // Final screenshot
    console.log('\n📸 Taking final screenshot...');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/99-final.png`, fullPage: true });
    console.log('✅ Screenshot: 99-final.png');

    // Print stage transition summary
    console.log('\n' + '='.repeat(60));
    console.log('STAGE TRANSITIONS DETECTED:');
    console.log('='.repeat(60));
    for (const trans of stageTransitions) {
      console.log(`${String(trans.time).padStart(5)}ms: ${String(trans.from || 'START').padStart(10)} → ${String(trans.to).padStart(10)} (${trans.progress}%)`);
    }
    console.log('='.repeat(60));

    // Verify key transitions
    const transition1to2 = stageTransitions.find(t => t.to === 'convert');
    const transition2to3 = stageTransitions.find(t => t.to === 'map');

    console.log('\n✅ KEY RESULTS:');
    if (transition1to2) {
      console.log(`✅ Stage 1→2 (upload→convert): Detected at ${transition1to2.time}ms`);
    } else {
      console.log('⚠️  Stage 1→2 transition not captured');
    }

    if (transition2to3) {
      console.log(`✅ Stage 2→3 (convert→map): Detected at ${transition2to3.time}ms`);
    } else {
      console.log('⚠️  Stage 2→3 transition not captured');
    }

    if (transition1to2 && transition2to3) {
      const timeBetween = transition2to3.time - transition1to2.time;
      console.log(`   (Stage 2 took ${timeBetween}ms)`);
    }

    console.log(`\n📂 Screenshots saved: ${path.resolve(SCREENSHOT_DIR)}`);

  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
      console.log('🔌 Browser closed\n');
    }
  }
}

runTest().catch(console.error);
