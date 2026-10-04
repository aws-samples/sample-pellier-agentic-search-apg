/** Scenario choice changes shopping context; it never authenticates a caller. */
import { expect, test } from '@playwright/test';
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000';

test.describe('Shopper scenario and identity boundary', () => {
  test('all three scenarios remain anonymous until a real sign-in', async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true'));
    await page.goto(BASE_URL);
    await page.getByTestId('persona-pill').click();
    const backdrop = page.getByTestId('persona-modal-backdrop');
    await backdrop.click({ position: { x: 10, y: 10 } });
    await expect(backdrop).toBeHidden();
    for (const name of ['marco', 'anna', 'theo']) {
      await page.getByTestId('persona-pill').click();
      const modal = page.getByTestId('persona-modal-backdrop');
      await expect(modal).toBeVisible();
      const box = await modal.boundingBox();
      expect(box).toMatchObject({ x: 0, y: 0, ...page.viewportSize() });
      expect(await modal.evaluate(el => el.parentElement?.tagName)).toBe('BODY');
      await page.getByTestId(`persona-card-${name}`).click();
      await expect(page.getByTestId('persona-pill')).toContainText(new RegExp(name, 'i'));
      const identity = await page.request.get(`${BASE_URL}/api/auth/me`);
      expect(identity.status()).toBe(401);
      const staffRead = await page.request.get(`${BASE_URL}/api/operator/clients`);
      expect(staffRead.status()).toBe(401);
    }
  });
});
