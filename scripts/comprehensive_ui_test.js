const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const ARTIFACTS_DIR = path.resolve(__dirname, 'screenshots');
if (!fs.existsSync(ARTIFACTS_DIR)) {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
}

const routesToTest = [
  { name: 'Dashboard', path: '/dashboard', label: 'Studio Dashboard' },
  { name: 'Studio', path: '/studio', label: 'Episode Studio Workspace' },
  { name: 'Projects', path: '/projects', label: 'Projects List' },
  { name: 'Episodes', path: '/episodes', label: 'Episodes List' },
  { name: 'Storyboard', path: '/storyboard', label: 'Storyboard Visuals' },
  { name: 'Characters', path: '/characters', label: 'Character Management' },
  { name: 'World / Setting', path: '/world', label: 'World Building & Lore' },
  { name: 'Assets', path: '/assets', label: 'Asset Library' },
  { name: 'Reviews', path: '/reviews', label: 'Review & Approvals' },
  { name: 'Agent Workspace', path: '/workspace', label: 'Agent Workspace / Chat' },
  { name: 'Router / Providers', path: '/router', label: 'Router & Provider Rules' },
  { name: 'Browser', path: '/browser', label: 'Browser Tool Integration' },
  { name: 'Files', path: '/files', label: 'File Manager' },
  { name: 'Settings', path: '/settings', label: 'Settings & Configurations' },
  { name: 'Agents', path: '/agents', label: 'Agent Definitions' },
  { name: 'Workflows', path: '/workflows', label: 'Workflows & DAGs' },
  { name: 'Monitoring', path: '/monitoring', label: 'System Telemetry & Metrics' },
  { name: 'Logs', path: '/logs', label: 'Runtime Logs' },
  { name: 'Memory', path: '/memory', label: 'Memory & Context Records' },
  { name: 'Models Library', path: '/models', label: 'Models Registry' }
];

async function runTestSuite() {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });

  const page = await context.newPage();
  const results = [];

  console.log('=== STARTING DEEP AUTOMATED UI TEST OF WINDAGENT ===\n');

  // Test each route
  for (const item of routesToTest) {
    const itemErrors = [];
    const itemNetworkErrors = [];

    const onConsole = msg => {
      if (msg.type() === 'error') itemErrors.push(msg.text());
    };
    const onResponse = res => {
      if (res.status() >= 400) itemNetworkErrors.push(`${res.status()} ${res.url()}`);
    };

    page.on('console', onConsole);
    page.on('response', onResponse);

    try {
      console.log(`\n========================================`);
      console.log(`Testing: ${item.name} (${item.path}) - ${item.label}`);
      console.log(`========================================`);

      await page.goto(`http://127.0.0.1:5173#${item.path}`, { waitUntil: 'networkidle', timeout: 10000 });
      await page.waitForTimeout(1000);

      // Check header / body content
      const bodyText = await page.textContent('body');
      const hasContent = bodyText && bodyText.length > 50;

      const buttons = await page.$$eval('button', els => els.map(e => e.innerText.trim()).filter(Boolean));
      const inputs = await page.$$eval('input, textarea, select', els => els.map(e => e.getAttribute('placeholder') || e.getAttribute('name') || e.tagName));

      // Capture screenshot
      const safeName = item.name.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
      const screenshotPath = path.join(ARTIFACTS_DIR, `${safeName}.png`);
      await page.screenshot({ path: screenshotPath });

      // Interactive actions per page
      const interactiveActions = [];

      // Specific interactions:
      if (item.path === '/dashboard') {
        const topStatus = await page.$eval('[class*="status"], [class*="badge"], header', el => el.innerText.slice(0, 100)).catch(() => 'N/A');
        interactiveActions.push(`Top header status: ${topStatus.replace(/\n/g, ' ')}`);
      }

      if (item.path === '/projects') {
        const createBtn = await page.$('button:has-text("Tạo dự án"), button:has-text("New Project"), button:has-text("Mẫu AI Starter")');
        if (createBtn) {
          const btnText = await createBtn.innerText();
          interactiveActions.push(`Found action button: "${btnText}"`);
        }
      }

      if (item.path === '/characters') {
        const addBtn = await page.$('button:has-text("Thêm Nhân Vật"), button:has-text("Add Character")');
        if (addBtn) {
          await addBtn.click();
          await page.waitForTimeout(600);
          const modal = await page.$('[role="dialog"], [class*="modal"], [class*="dialog"], form');
          interactiveActions.push(`Clicked 'Thêm Nhân Vật' -> Modal open: ${!!modal}`);
          const closeBtn = await page.$('button:has-text("Hủy"), button:has-text("Cancel"), button:has-text("Đóng")');
          if (closeBtn) await closeBtn.click();
        }
      }

      if (item.path === '/world') {
        const tabBtns = await page.$$eval('button:has-text("Tổng quan"), button:has-text("Địa điểm"), button:has-text("Phe phái")', els => els.map(e => e.innerText.trim()));
        interactiveActions.push(`World tabs active: ${tabBtns.join(', ')}`);
      }

      if (item.path === '/workspace') {
        const chatInput = await page.$('textarea, input[placeholder*="Ask"], input[placeholder*="message"], input[type="text"]');
        if (chatInput) {
          await chatInput.fill('Kiểm tra kết nối WindAgent');
          interactiveActions.push('Filled prompt input in Agent Workspace');
          const sendBtn = await page.$('button:has-text("Send"), button[type="submit"], button:has-text("Gửi")');
          if (sendBtn) {
            await sendBtn.click();
            await page.waitForTimeout(1000);
            interactiveActions.push('Triggered Send prompt button');
          }
        }
      }

      if (item.path === '/router') {
        const tabs = await page.$$eval('button:has-text("Routing"), button:has-text("Rules"), button:has-text("Graph"), button:has-text("Simulator")', els => els.map(e => e.innerText.trim()));
        interactiveActions.push(`Router tabs: ${tabs.join(', ')}`);
      }

      if (item.path === '/browser') {
        const urlInput = await page.$('input[placeholder*="URL"], input[placeholder*="http"]');
        if (urlInput) {
          await urlInput.fill('https://example.com');
          interactiveActions.push('Filled URL in Browser tool input');
        }
      }

      if (item.path === '/settings') {
        const themeBtns = await page.$$eval('button:has-text("dark"), button:has-text("light"), button:has-text("system")', els => els.map(e => e.innerText.trim()));
        interactiveActions.push(`Theme buttons: ${themeBtns.join(', ')}`);
      }

      if (item.path === '/monitoring') {
        const refreshBtn = await page.$('button:has-text("Làm Mới"), button:has-text("Refresh")');
        if (refreshBtn) {
          await refreshBtn.click();
          await page.waitForTimeout(500);
          interactiveActions.push('Clicked "Làm Mới" metrics button');
        }
      }

      if (item.path === '/logs') {
        const selects = await page.$$eval('select', els => els.map(e => Array.from(e.options).map(o => o.value).join(',')));
        interactiveActions.push(`Logs filter dropdowns options: ${selects.join(' | ')}`);
      }

      if (item.path === '/memory') {
        const memInput = await page.$('input[placeholder*="Search"], input[placeholder*="Tìm"]');
        if (memInput) {
          await memInput.fill('test memory');
          interactiveActions.push('Filled search query in Memory search input');
        }
      }

      let status = 'PASS';
      const details = [];

      if (!hasContent) {
        status = 'FAIL';
        details.push('Page body is blank or empty');
      }

      const criticalErrors = itemErrors.filter(e =>
        e.includes('Cannot read properties') ||
        e.includes('undefined is not an object') ||
        e.includes('Uncaught') ||
        e.includes('Error on route')
      );

      if (criticalErrors.length > 0) {
        status = 'FAIL';
        details.push(`Critical JS Error: ${criticalErrors.join('; ')}`);
      } else if (itemErrors.length > 0) {
        details.push(`Minor console logs: ${itemErrors.slice(0, 2).join('; ')}`);
        if (status !== 'FAIL') status = 'WARNING';
      }

      if (itemNetworkErrors.length > 0) {
        details.push(`HTTP network errors: ${itemNetworkErrors.slice(0, 3).join(', ')}`);
        if (status !== 'FAIL') status = 'WARNING';
      }

      console.log(`Result: [${status}]`);
      console.log(`Visible Buttons (${buttons.length}):`, buttons.slice(0, 8).join(' | ') || 'None');
      console.log(`Inputs (${inputs.length}):`, inputs.slice(0, 5).join(' | ') || 'None');
      if (interactiveActions.length > 0) {
        console.log(`Interactions:`, interactiveActions.join(' | '));
      }
      if (details.length > 0) {
        console.log(`Notes/Issues:`, details.join(' | '));
      }

      results.push({
        feature: item.name,
        path: item.path,
        label: item.label,
        status,
        buttonCount: buttons.length,
        buttons: buttons.slice(0, 10),
        inputCount: inputs.length,
        inputs: inputs.slice(0, 5),
        interactiveActions,
        consoleErrors: itemErrors,
        networkErrors: itemNetworkErrors,
        screenshot: screenshotPath,
        details
      });

    } catch (err) {
      console.error(`[FAIL] ${item.name}: ${err.message}`);
      results.push({
        feature: item.name,
        path: item.path,
        label: item.label,
        status: 'FAIL',
        error: err.message,
        details: [err.message]
      });
    } finally {
      page.off('console', onConsole);
      page.off('response', onResponse);
    }
  }

  console.log('\n=== COMPLETE TEST SUMMARY ===');
  console.table(results.map(r => ({
    Feature: r.feature,
    Path: r.path,
    Status: r.status,
    Buttons: r.buttonCount || 0,
    Inputs: r.inputCount || 0,
    Issues: (r.details || []).join('; ') || 'None'
  })));

  fs.writeFileSync(
    path.join(__dirname, 'ui_test_results.json'),
    JSON.stringify({ timestamp: new Date().toISOString(), results }, null, 2)
  );

  await browser.close();
}

runTestSuite().catch(console.error);
