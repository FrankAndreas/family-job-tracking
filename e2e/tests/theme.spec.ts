import { expect, test } from '@playwright/test';
import { mockApi } from './api';

// Themes (family-hub design 2026-11-28): the family look from family-hub-theme, with the person's theme from the hub
test('the page loads theme-init.js', async ({ request }) => {
    const response = await request.get('/theme-init.js');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('javascript');
    expect(await response.text()).toContain('family-theme');
});

test('the person theme is applied after login', async ({ page }) => {
    const unknown = await mockApi(page);
    await page.goto('/theme-init.js');
    await page.evaluate(() => localStorage.removeItem('family-theme'));
    await page.goto('/');
    await expect(page.getByText('Muster Elektro AG').first()).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'aurora');
    // Applied from who is logged in (written to storage), not only from the last page load
    await expect.poll(() => page.evaluate(() => localStorage.getItem('family-theme'))).toBe('aurora');
    expect(unknown).toEqual([]);
});

test('the cards are the family look: glass', async ({ page }) => {
    const unknown = await mockApi(page);
    await page.goto('/');
    await expect(page.getByText('Muster Elektro AG').first()).toBeVisible();
    // Asked again until it holds: a card being replaced while the page loads has no style
    await expect.poll(() => page.locator('.glass-card').first().evaluate((e) => getComputedStyle(e).backdropFilter)).toContain('blur');
    expect(unknown).toEqual([]);
});
