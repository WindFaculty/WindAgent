const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true
  });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5173#/projects', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.click('button:has-text("Tạo dự án mới")');
  await page.waitForTimeout(800);
  await page.fill('input[placeholder*="Cyberpunk"]', 'Dự án Phim Hoạt Hình 3D Test UI');
  await page.click('form button:has-text("Tạo dự án")');
  await page.waitForTimeout(1500);
  console.log('URL after creation:', page.url());
  const bodyText = await page.textContent('body');
  const projectCreated = bodyText.includes('Dự án Phim Hoạt Hình 3D Test UI');
  console.log('Project created and visible on UI:', projectCreated);
  await browser.close();
})();
