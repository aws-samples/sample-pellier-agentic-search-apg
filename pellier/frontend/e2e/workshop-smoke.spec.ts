/** Public participant navigation. No fixture interception or model-success claims.
 * Run against the intended deployment with E2E_BASE_URL. Authenticated Runtime,
 * Memory, writes, and output suppression require separate authenticated live checks.
 */
import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true');
  });
});

test.describe('Public governed workshop journey', () => {

  test('fonts are self-hosted', async ({ page }) => {
    const thirdPartyAssets: string[] = [];
    page.on('request', request => {
      const host = new URL(request.url()).hostname;
      if (['fonts.gstatic.com', 'fonts.googleapis.com'].includes(host)) thirdPartyAssets.push(request.url());
    });
    await page.goto(BASE_URL);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    expect(thirdPartyAssets).toEqual([]);
  });

  test('a signed-out Operator route requests identity and preserves the destination', async ({ page }) => {
    await page.goto(`${BASE_URL}/operator/clients/CUST-JESSICA?guided=service-recovery`);
    await expect(page.getByTestId('operator-sign-in')).toBeVisible();
    await page.getByTestId('operator-sign-in').click();
    await expect(page.getByTestId('pellier-signin')).toBeVisible();
    await expect(page).toHaveURL(/returnTo=.*operator/);
    await expect(page.getByTestId('operator-record')).toHaveCount(0);
    const protectedRead = await page.request.get(`${BASE_URL}/api/operator/clients`);
    expect(protectedRead.status()).toBe(401);
  });

  test('the reset link clears persisted browser state and removes the reset flag', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.evaluate(() => localStorage.setItem('smoke-test-key', 'previous-session'));
    await page.goto(`${BASE_URL}/?reset=1`);
    await expect(page).toHaveURL(new URL('/', BASE_URL).toString());
    await expect.poll(() => page.evaluate(() => localStorage.getItem('smoke-test-key'))).toBeNull();
  });

  for (const width of [1440, 1024, 390]) {
    test(`reference journey has readable headings and no document overflow at ${width}px`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      for (const route of ['/', '/about', '/storyboard', '/product/2', '/operator']) {
        await page.goto(`${BASE_URL}${route}`);
        await expect(page.getByRole('heading', { level: 1 }).first(), route).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), route).toBe(true);
      }
      expect(errors).toEqual([]);
    });
  }
});
