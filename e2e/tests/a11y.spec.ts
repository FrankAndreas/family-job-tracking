import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { mockApi } from './api';

// Accessibility review 2026-11-08: axe finds nothing on any page or state, so a change that breaks a label, a contrast
// or a heading fails here
async function noViolations(page: Page, state: string) {
    const { violations } = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
        .analyze();
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`), state).toEqual([]);
}

let unknown: string[];
test.beforeEach(async ({ page }) => {
    unknown = await mockApi(page);
});
test.afterEach(() => {
    expect(unknown, 'API requests the tests do not answer (tests/api.ts)').toEqual([]);
});

test('overview', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Muster Elektro AG').first()).toBeVisible();
    await noViolations(page, 'overview');
    // A tile filters the list; pressed or not is said, not only shown by its border
    const offers = page.getByRole('button', { name: /Zusagen/ });
    await expect(offers).toHaveAttribute('aria-pressed', 'false');
    await offers.click();
    await expect(offers).toHaveAttribute('aria-pressed', 'true');
    await page.getByLabel('Archivierte zeigen').check();
    await page.getByRole('button', { name: 'Neue Bewerbung' }).click();
    await noViolations(page, 'overview with filter, archived and the new application form');
});

test('application', async ({ page }) => {
    await page.goto('/bewerbungen/1');
    await expect(page.getByRole('heading', { level: 1, name: 'Muster Elektro AG' })).toBeVisible();
    await noViolations(page, 'application');
    await page.getByRole('button', { name: 'bearbeiten' }).first().click();
    await page.getByRole('button', { name: '+ Ereignis' }).click();
    await noViolations(page, 'editing an event, and the new event form');
});

test('suggestions, inbox, documents, settings', async ({ page }) => {
    await page.goto('/vorschlaege');
    await expect(page.getByText('Werkstatt Beispiel').first()).toBeVisible();
    await noViolations(page, 'suggestions');

    await page.goto('/posteingang');
    await expect(page.getByText('Einladung zum Schnuppern')).toBeVisible();
    await page.getByRole('button', { name: 'Neue Bewerbung daraus erstellen' }).click();
    await noViolations(page, 'inbox with the new application fields');

    await page.goto('/unterlagen');
    await expect(page.getByText('Multicheck')).toBeVisible();
    await noViolations(page, 'documents');
    await page.getByRole('button', { name: /bearbeiten/i }).first().click();
    await noViolations(page, 'editing a document');

    await page.goto('/einstellungen');
    await expect(page.getByText('Resend antwortet nicht')).toBeVisible();
    await noViolations(page, 'settings');
});

test('no access, and the hub out of reach', async ({ page }) => {
    await page.route('**/api/me', (route) => route.fulfill({ status: 403, json: { detail: 'no_access' } }));
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Kein Zugang' })).toBeVisible();
    await noViolations(page, 'no access');
    await page.route('**/api/me', (route) => route.fulfill({ status: 503, json: { detail: 'hub_unavailable' } }));
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Anmelden geht gerade nicht' })).toBeVisible();
    await noViolations(page, 'hub out of reach');
});

// Screen readers: the tab names the page, moving to another page reads its heading, the red dot is said in words
test('pages are announced', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Bewerbungen');
    const settings = page.getByRole('link', { name: 'Einstellungen (eine Integration meldet einen Fehler)' });
    await settings.click();
    await expect(page).toHaveTitle('Einstellungen · Bewerbungen');
    await expect(page.getByRole('heading', { level: 1, name: 'Einstellungen' })).toBeFocused();
    await page.getByRole('link', { name: /^Posteingang/ }).click();
    await expect(page).toHaveTitle('Posteingang · Bewerbungen');
    await expect(page.getByRole('heading', { level: 1, name: 'Posteingang' })).toBeFocused();
    await page.getByRole('link', { name: /^Übersicht/ }).click();
    await page.getByRole('link', { name: /Muster Elektro AG/ }).last().click();
    // Loaded after the navigation: its heading gets the focus once it is there
    await expect(page.getByRole('heading', { level: 1, name: 'Muster Elektro AG' })).toBeFocused();
    await expect(page).toHaveTitle('Muster Elektro AG · Bewerbungen');
});

// Nothing wider than the screen, on a phone too (WCAG reflow): the navigation once was, and every page scrolled sideways
test('fits the screen', async ({ page }) => {
    for (const path of ['/', '/bewerbungen/1', '/vorschlaege', '/posteingang', '/unterlagen', '/einstellungen']) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const [width, scrolled] = await page.evaluate(() => [document.documentElement.clientWidth, document.documentElement.scrollWidth]);
        expect(scrolled, path).toBeLessThanOrEqual(width);
    }
});

// An error stays until closed, announced as an alert; the same one twice shows once
test('errors stay until closed', async ({ page }) => {
    await page.route('**/api/inbox/21/dismiss', (route) => route.fulfill({ status: 500, json: { detail: 'Kaputt' } }));
    await page.goto('/posteingang');
    page.on('dialog', (dialog) => void dialog.accept());
    const dismiss = page.getByRole('button', { name: 'Verwerfen' });
    await dismiss.click();
    await dismiss.click();
    const alert = page.getByRole('alert');
    await expect(alert).toHaveText(/Kaputt/);
    await expect(alert.getByRole('button', { name: 'Meldung schliessen' })).toHaveCount(1);
    await page.waitForTimeout(5500);
    await expect(alert).toHaveText(/Kaputt/);
    await noViolations(page, 'an error message');
    await alert.getByRole('button', { name: 'Meldung schliessen' }).click();
    await expect(alert).toHaveText('');
});
