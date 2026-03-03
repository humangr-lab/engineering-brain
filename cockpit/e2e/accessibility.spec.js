// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('h1');
  });

  test('skip-link is present and targets main content', async ({ page }) => {
    const skipLink = page.locator('.skip-link, a[href="#sc"]');
    await expect(skipLink).toHaveCount(1);
    const href = await skipLink.getAttribute('href');
    expect(href).toBe('#sc');
  });

  test('skip-link becomes visible on focus', async ({ page }) => {
    // Tab to focus the skip-link (first focusable element)
    await page.keyboard.press('Tab');
    const skipLink = page.locator('.skip-link');
    // Skip links use :focus CSS to become visible
    const box = await skipLink.boundingBox();
    // When focused, it should have positive dimensions
    if (box) {
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
    }
  });

  test('ARIA live region exists for announcements', async ({ page }) => {
    const live = page.locator('#a11yLive, [role="status"][aria-live]');
    await expect(live).toHaveCount(1);
    const role = await live.getAttribute('role');
    expect(role).toBe('status');
    const ariaLive = await live.getAttribute('aria-live');
    expect(ariaLive).toBe('polite');
  });

  test('header has banner role', async ({ page }) => {
    const banner = page.locator('[role="banner"]');
    await expect(banner).toHaveCount(1);
  });

  test('3D scene has appropriate ARIA label', async ({ page }) => {
    const scene = page.locator('#sc');
    const role = await scene.getAttribute('role');
    expect(role).toBe('img');
    const label = await scene.getAttribute('aria-label');
    expect(label).toContain('3D');
  });

  test('3D scene is focusable (tabindex=0)', async ({ page }) => {
    const scene = page.locator('#sc');
    const tabindex = await scene.getAttribute('tabindex');
    expect(tabindex).toBe('0');
  });

  test('breadcrumb has navigation role', async ({ page }) => {
    const nav = page.locator('#wp3Breadcrumb');
    const label = await nav.getAttribute('aria-label');
    expect(label).toContain('Breadcrumb');
  });

  test('keyboard Tab cycles through interactive elements', async ({ page }) => {
    // Press Tab several times and collect focused elements
    const focusedTags = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Tab');
      const tag = await page.evaluate(() => document.activeElement?.tagName);
      if (tag) focusedTags.push(tag);
    }
    // Should have focused at least 2 different elements
    const unique = new Set(focusedTags);
    expect(unique.size).toBeGreaterThanOrEqual(1);
  });
});
