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
      const identity = await page.request.get(`${BASE_URL}/api/observatory/governance/identity`);
      expect(identity.status()).toBe(200);
      expect((await identity.json()).state).toBe('anonymous');
      const staffEvidence = await page.request.get(`${BASE_URL}/api/observatory/governance/outcomes`);
      expect(staffEvidence.status()).toBe(401);
    }
  });
});
