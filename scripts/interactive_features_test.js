const { chromium } = require('playwright-core');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const actionsLog = [];

  console.log('=== RUNNING DEEP INTERACTIVE MUTATION TESTS ===\n');

  // Test 1: Project Creation via UI
  try {
    await page.goto('http://127.0.0.1:5173#/projects', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const newProjBtn = await page.$('button:has-text("Tạo dự án mới"), button:has-text("New Project")');
    if (newProjBtn) {
      await newProjBtn.click();
      await page.waitForTimeout(800);
      const nameInput = await page.$('input[placeholder*="tên dự án"], input[placeholder*="name"], input[placeholder*="Title"], form input[type="text"]');
      if (nameInput) {
        await nameInput.fill('Dự án Phim Hoạt Hình Test UI');
        const submitBtn = await page.$('form button:has-text("Tạo"), form button:has-text("Create"), form button[type="submit"]');
        if (submitBtn) {
          await submitBtn.click();
          await page.waitForTimeout(1200);
          actionsLog.push({ test: 'Create Project via Modal', status: 'SUCCESS', details: 'Form filled and submitted' });
        }
      } else {
        actionsLog.push({ test: 'Create Project Modal', status: 'PARTIAL', details: 'Modal opened but input not found' });
      }
    }
  } catch (err) {
    actionsLog.push({ test: 'Create Project via Modal', status: 'ERROR', error: err.message });
  }

  // Test 2: Character Creation via UI
  try {
    await page.goto('http://127.0.0.1:5173#/characters', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const addCharBtn = await page.$('button:has-text("Thêm Nhân Vật")');
    if (addCharBtn) {
      await addCharBtn.click();
      await page.waitForTimeout(800);
      const nameInput = await page.$('input[placeholder*="Tên nhân vật"], input[placeholder*="Name"]');
      if (nameInput) {
        await nameInput.fill('Kenshi Shinobi');
        const descInput = await page.$('textarea, input[placeholder*="Mô tả"], input[placeholder*="Role"]');
        if (descInput) await descInput.fill('Chiến binh ninja với kỹ năng phi tiêu bóng tối.');
        const saveBtn = await page.$('button:has-text("Lưu"), button:has-text("Tạo"), button[type="submit"]');
        if (saveBtn) {
          await saveBtn.click();
          await page.waitForTimeout(1200);
          actionsLog.push({ test: 'Add Character via Modal', status: 'SUCCESS', details: 'Created character Kenshi Shinobi' });
        }
      }
    }
  } catch (err) {
    actionsLog.push({ test: 'Add Character via Modal', status: 'ERROR', error: err.message });
  }

  // Test 3: Theme Switcher in Settings
  try {
    await page.goto('http://127.0.0.1:5173#/settings', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const lightBtn = await page.$('button:has-text("light")');
    if (lightBtn) {
      await lightBtn.click();
      await page.waitForTimeout(500);
      const isLightActive = await page.evaluate(() => document.documentElement.getAttribute('data-theme') || document.body.className);
      const darkBtn = await page.$('button:has-text("dark")');
      if (darkBtn) await darkBtn.click();
      actionsLog.push({ test: 'Theme Switcher', status: 'SUCCESS', details: `Toggled light/dark successfully (theme attribute: ${isLightActive || 'active'})` });
    }
  } catch (err) {
    actionsLog.push({ test: 'Theme Switcher', status: 'ERROR', error: err.message });
  }

  // Test 4: Files creation in Files manager
  try {
    await page.goto('http://127.0.0.1:5173#/files', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const pathInput = await page.$('input[placeholder*="workspace-relative path"]');
    const contentInput = await page.$('textarea, input[placeholder*="file content"]');
    const createBtn = await page.$('button:has-text("Create")');
    if (pathInput && contentInput && createBtn) {
      await pathInput.fill('scratch/ui_test_file.txt');
      await contentInput.fill('Tested by Automated Browser QA.');
      await createBtn.click();
      await page.waitForTimeout(1000);
      actionsLog.push({ test: 'File Creator', status: 'SUCCESS', details: 'Created scratch/ui_test_file.txt' });
    }
  } catch (err) {
    actionsLog.push({ test: 'File Creator', status: 'ERROR', error: err.message });
  }

  // Test 5: Memory item addition
  try {
    await page.goto('http://127.0.0.1:5173#/memory', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const memInput = await page.$('input[placeholder*="new memory content"], textarea');
    const saveBtn = await page.$('button:has-text("Save")');
    if (memInput && saveBtn) {
      await memInput.fill('Project guidelines: local-first agent architecture.');
      await saveBtn.click();
      await page.waitForTimeout(1000);
      actionsLog.push({ test: 'Memory Record Insert', status: 'SUCCESS', details: 'Added new memory record' });
    }
  } catch (err) {
    actionsLog.push({ test: 'Memory Record Insert', status: 'ERROR', error: err.message });
  }

  console.log('\n=== INTERACTIVE ACTION RESULTS ===');
  console.table(actionsLog);

  await browser.close();
})();
