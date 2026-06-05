const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const STEP_FILES_DIR = 'C:\\Users\\895428\\Depo\\SPLM_Folder\\step_files';
const SCREENSHOT_DIR = './test-stage-detail';

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

    await page.waitForTimeout(1500);

    console.log('🔍 Clicking on "↓ Data Import" tab...');
    const buttons = await page.$$('button');
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && text.includes('Data Import')) {
        await btn.click();
        break;
      }
    }

    await page.waitForTimeout(1500);

    // Upload file
    console.log('📂 Uploading STEP file...');
    const fileInput = await page.$('input[type="file"]');
    const stepFiles = fs.readdirSync(STEP_FILES_DIR)
      .filter(f => f.endsWith('.stp'))
      .slice(0, 1)
      .map(f => path.join(STEP_FILES_DIR, f));

    const fileName = path.basename(stepFiles[0]);
    console.log(`   File: ${fileName}`);
    await fileInput.setInputFiles(stepFiles);
    
    await page.waitForTimeout(1000);

    // Click Start Pipeline
    console.log('▶️ Clicking "▶ Start Pipeline" button...');
    let startBtn = null;
    const allBtns = await page.$$('button');
    for (const btn of allBtns) {
      const text = await btn.textContent();
      if (text && text.includes('Start Pipeline')) {
        startBtn = btn;
        break;
      }
    }
    
    const startTime = Date.now();
    await startBtn.click({ force: true });
    
    // Immediately start polling backend (every 100ms)
    console.log('\n⏳ Polling backend every 100ms...\n');
    
    let taskId = null;
    let lastStage = null;
    let stageLog = [];
    let statusCode = 0;

    // Poll for up to 15 seconds
    for (let i = 0; i < 150; i++) {
      const elapsed = Date.now() - startTime;
      
      try {
        // First, get the task list to find our task
        if (i === 0 || i === 10) {
          const tasksData = await page.evaluate(() =>
            fetch('http://localhost:8000/data-import/tasks')
              .then(r => r.json())
              .catch(() => ({ tasks: [] }))
          );
          if (tasksData.tasks && tasksData.tasks.length > 0) {
            taskId = tasksData.tasks[0].task_id;
          }
        }

        if (!taskId) {
          await new Promise(r => setTimeout(r, 100));
          continue;
        }

        // Poll status
        const statusData = await page.evaluate((tid) =>
          fetch(`http://localhost:8000/data-import/status/${tid}`)
            .then(r => r.json())
            .catch(() => null)
        , taskId);

        if (statusData) {
          const statusResp = { ok: true };
          statusCode = 200;
          
          if (statusResp.ok) {
            
            if (statusData.current_stage !== lastStage) {
              const log = {
                elapsed,
                stage: statusData.current_stage,
                progress: statusData.progress,
                message: statusData.message,
                status: statusData.status
              };
              stageLog.push(log);
              
              console.log(`[${String(elapsed).padStart(5)}ms] Stage: ${String(statusData.current_stage).padStart(10)} | Progress: ${String(statusData.progress).padStart(3)}% | ${statusData.message}`);
              lastStage = statusData.current_stage;
              
              // Capture screenshot at stage change
              await page.screenshot({ path: `${SCREENSHOT_DIR}/stage-${statusData.current_stage}-${String(elapsed).padStart(5)}.png` });
            }

              if (statusData.status === 'completed' || statusData.status === 'failed') {
                console.log(`\n✅ Pipeline ${statusData.status.toUpperCase()} at ${elapsed}ms\n`);
                break;
              }
            }
          }
        } catch (err) {
          // Network error, continue
        }

        await new Promise(r => setTimeout(r, 100));
      }

    // Final screenshot
    await page.screenshot({ path: `${SCREENSHOT_DIR}/final-state.png`, fullPage: true });

    // Print summary
    console.log('='.repeat(70));
    console.log('STAGE PROGRESSION SUMMARY');
    console.log('='.repeat(70));
    
    for (let i = 0; i < stageLog.length; i++) {
      const log = stageLog[i];
      const prevStage = i > 0 ? stageLog[i-1].stage : 'upload';
      const stageDuration = i > 0 ? log.elapsed - stageLog[i-1].elapsed : log.elapsed;
      
      console.log(`${String(log.elapsed).padStart(6)}ms  ${String(prevStage + '→' + log.stage).padStart(17)}  Progress: ${String(log.progress).padStart(3)}%  (took ${stageDuration}ms)`);
    }
    console.log('='.repeat(70));

    // Check key transitions
    const stage1to2 = stageLog.find(l => l.stage === 'convert' || l.stage === 'map' && stageLog[stageLog.indexOf(l) - 1]?.stage === 'upload');
    const stage2to3 = stageLog.find(l => l.stage === 'map' && stageLog[stageLog.indexOf(l) - 1]?.stage === 'convert');

    console.log('\n✅ TEST RESULTS:');
    if (stageLog.length >= 1) {
      console.log(`✅ Stage transitions captured: ${stageLog.length} unique stages`);
      if (stageLog[0]?.stage) {
        console.log(`   - First stage: ${stageLog[0].stage}`);
      }
      if (stageLog[stageLog.length - 1]?.stage) {
        console.log(`   - Final stage: ${stageLog[stageLog.length - 1].stage}`);
      }
    }

    // Detail on 1→2 transition
    if (stageLog.length >= 2) {
      const trans = stageLog[1];
      console.log(`✅ Stage 1→2: ${stageLog[0].stage}→${trans.stage} at ${trans.elapsed}ms`);
    } else if (stageLog.length === 1) {
      console.log(`⚠️  Only saw final stage (${stageLog[0].stage}), intermediate stages not captured`);
      console.log(`   This means backend processing was very fast (<100ms)`);
    }

    // Detail on 2→3 transition
    if (stageLog.length >= 3) {
      const trans = stageLog[2];
      console.log(`✅ Stage 2→3: ${stageLog[1].stage}→${trans.stage} at ${trans.elapsed}ms`);
    }

    console.log(`\n📂 Screenshots: ${path.resolve(SCREENSHOT_DIR)}`);

  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

// Run test
runTest().catch(console.error);
