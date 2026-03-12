/**
 * Debug script: capture console errors and check visible state of the page.
 */
const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const errors = [];
  const logs = [];

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    if (type === 'error') errors.push(text);
    else logs.push(`[${type}] ${text}`);
  });
  page.on('pageerror', err => errors.push('PAGE ERROR: ' + err.message));

  await page.goto('https://karlstad-events.surge.sh', { waitUntil: 'networkidle' });

  // Wait a moment for JS to run
  await page.waitForTimeout(2000);

  const eventCount = await page.locator('.event-item').count();
  const pillCount  = await page.locator('.filter-pill').count();
  const footerText = await page.locator('#event-count').textContent().catch(() => 'N/A');
  const listHTML   = await page.locator('#event-list').innerHTML();

  console.log('=== DEBUG REPORT ===');
  console.log('Event items visible:', eventCount);
  console.log('Filter pills visible:', pillCount);
  console.log('Footer count text:', footerText);
  console.log('event-list first 300 chars:', listHTML.slice(0, 300) || '(empty)');
  console.log('');
  console.log('Console errors:', errors.length ? errors : 'none');
  console.log('Console logs (first 20):', logs.slice(0, 20));

  if (eventCount === 0) {
    // Try evaluating the JS in-browser
    const result = await page.evaluate(() => {
      const evts = window.__EVENTS__;
      if (!evts) return { error: '__EVENTS__ is undefined' };
      const today = new Date().toISOString().slice(0, 10);
      const future = evts.filter(e => e.date >= today || (e.end_date && e.end_date >= today));
      return {
        total: evts.length,
        futureCount: future.length,
        todayIso: today,
        firstEvent: future[0] || null,
        firstDate: future[0]?.date || 'N/A',
      };
    });
    console.log('');
    console.log('In-browser evaluation:', JSON.stringify(result, null, 2));
  }

  await browser.close();
})();
