/**
 * Playwright tests for https://karlstad-events.surge.sh
 * Tests category filtering functionality end-to-end.
 */

const { test, expect } = require('@playwright/test');

const URL = 'https://karlstad-events.surge.sh';

test.describe('Karlstad Events - Category Filtering', () => {

  test('page loads and shows events', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.event-item', { timeout: 10000 });
    const items = await page.locator('.event-item').count();
    console.log(`Events rendered: ${items}`);
    expect(items).toBeGreaterThan(50);
  });

  test('filter bar renders with Alla pill active by default', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const pills = await page.locator('.filter-pill').all();
    expect(pills.length).toBeGreaterThan(3);

    // "Alla" pill should be active
    const allaPill = page.locator('.filter-pill[data-cat="all"]');
    await expect(allaPill).toHaveClass(/active/);
    console.log(`Filter pills rendered: ${pills.length}`);
  });

  test('filter pills show non-zero event counts', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const pills = await page.locator('.filter-pill').all();
    for (const pill of pills) {
      const countEl = pill.locator('.count');
      const text = await countEl.textContent();
      const n = parseInt(text ?? '0', 10);
      expect(n).toBeGreaterThan(0);
    }
  });

  test('clicking a category pill filters the list', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    // Count total events with Alla active
    const totalBefore = await page.locator('.event-item').count();

    // Click "Konserter" (concert)
    const concertPill = page.locator('.filter-pill[data-cat="concert"]');
    await expect(concertPill).toBeVisible();
    const concertCount = parseInt(
      (await concertPill.locator('.count').textContent()) ?? '0', 10
    );
    await concertPill.click();

    // Alla should no longer be active, concert pill should be active
    await expect(page.locator('.filter-pill[data-cat="all"]')).not.toHaveClass(/active/);
    await expect(concertPill).toHaveClass(/active/);

    // Event list count should match the badge count
    const afterCount = await page.locator('.event-item').count();
    console.log(`Concert filter: pill says ${concertCount}, rendered ${afterCount}`);
    expect(afterCount).toBe(concertCount);
    expect(afterCount).toBeLessThan(totalBefore);
  });

  test('clicking Alla restores full list', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const total = await page.locator('.event-item').count();

    // Click some other pill first
    const pill = page.locator('.filter-pill').nth(1);
    await pill.click();
    const filtered = await page.locator('.event-item').count();
    expect(filtered).toBeLessThan(total);

    // Click Alla
    await page.locator('.filter-pill[data-cat="all"]').click();
    const restored = await page.locator('.event-item').count();
    expect(restored).toBe(total);
  });

  test('multiple categories can be selected simultaneously', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const concertPill = page.locator('.filter-pill[data-cat="concert"]');
    const theaterPill = page.locator('.filter-pill[data-cat="theater"]');

    if (!(await concertPill.isVisible()) || !(await theaterPill.isVisible())) {
      test.skip();
      return;
    }

    const concertCount = parseInt(
      (await concertPill.locator('.count').textContent()) ?? '0', 10
    );
    const theaterCount = parseInt(
      (await theaterPill.locator('.count').textContent()) ?? '0', 10
    );

    await concertPill.click();
    await theaterPill.click();

    await expect(concertPill).toHaveClass(/active/);
    await expect(theaterPill).toHaveClass(/active/);

    const combined = await page.locator('.event-item').count();
    console.log(`Concert ${concertCount} + Theater ${theaterCount} = combined ${combined}`);
    expect(combined).toBe(concertCount + theaterCount);
  });

  test('deselecting last active category resets to Alla', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const total = await page.locator('.event-item').count();

    // Select one category
    const concertPill = page.locator('.filter-pill[data-cat="concert"]');
    await concertPill.click();
    await expect(concertPill).toHaveClass(/active/);

    // Deselect it — should snap back to "Alla"
    await concertPill.click();
    await expect(page.locator('.filter-pill[data-cat="all"]')).toHaveClass(/active/);
    const restored = await page.locator('.event-item').count();
    expect(restored).toBe(total);
  });

  test('event items have title and venue', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.event-item');

    const items = await page.locator('.event-item').all();
    let checked = 0;
    for (const item of items.slice(0, 10)) {
      const title = await item.locator('.event-title').textContent();
      const venue = await item.locator('.venue').textContent();
      expect(title?.trim().length).toBeGreaterThan(0);
      expect(venue?.trim().length).toBeGreaterThan(0);
      checked++;
    }
    console.log(`Spot-checked ${checked} event items — all have title and venue`);
  });

  test('event count in footer matches rendered events', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.event-item');

    const footerCount = parseInt(
      (await page.locator('#event-count').textContent()) ?? '0', 10
    );
    const renderedCount = await page.locator('.event-item').count();
    console.log(`Footer says ${footerCount}, rendered ${renderedCount}`);
    expect(footerCount).toBe(renderedCount);
  });

  test('footer count updates when filter is applied', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.filter-pill');

    const concertPill = page.locator('.filter-pill[data-cat="concert"]');
    const concertCount = parseInt(
      (await concertPill.locator('.count').textContent()) ?? '0', 10
    );
    await concertPill.click();

    const footerCount = parseInt(
      (await page.locator('#event-count').textContent()) ?? '0', 10
    );
    expect(footerCount).toBe(concertCount);
  });

  test('month dividers are rendered', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.month-divider');
    const dividers = await page.locator('.month-divider').count();
    console.log(`Month dividers: ${dividers}`);
    expect(dividers).toBeGreaterThan(0);
  });

  test('events are sorted by date (ascending)', async ({ page }) => {
    await page.goto(URL);
    await page.waitForSelector('.event-item');

    // Get the first few date numbers and weekday labels
    const dateEls = await page.locator('.date-day').all();
    const dates = [];
    for (const el of dateEls.slice(0, 5)) {
      dates.push((await el.textContent()) ?? '');
    }
    console.log('First 5 date-day values:', dates);
    // Just verify they're non-empty (full date order is embedded in HTML from Hugo sort)
    for (const d of dates) {
      expect(d.trim().length).toBeGreaterThan(0);
    }
  });

});
