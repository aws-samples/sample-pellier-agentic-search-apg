/** Public participant navigation. No fixture interception or model-success claims.
 * Run against the intended deployment with E2E_BASE_URL. Authenticated Runtime,
 * Memory, writes, and output suppression require the separate fresh-account proof.
 */
import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000';
const LABS = ['grounded-inventory', 'retrieval-acceptance', 'managed-agent-path', 'fail-closed-policy'];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true');
    sessionStorage.setItem('observatory-spotlight-seen', 'true');
  });
});

test.describe('Public governed workshop journey', () => {
  test('Storefront opens the four-lab collection and returns to the shop', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(BASE_URL);
    await expect(page.getByRole('link', { name: 'Pellier home', exact: true }).first()).toBeVisible();
    await page.getByRole('navigation', { name: 'Pellier surfaces' }).getByRole('link', { name: 'Observatory', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Governed Lab Collection' })).toBeVisible();
    await expect(page.locator('.labs-catalog-card')).toHaveCount(4);
    for (let i = 0; i < LABS.length; i++) {
      await page.getByRole('link', { name: `Open Lab ${i + 1} in Workbench`, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`lab=${LABS[i]}`));
      await expect(page.getByRole('heading', { name: 'Workbench', exact: true })).toBeVisible();
      await expect(page.getByText(`Follow Lab ${i + 1} in Workshop Studio.`, { exact: false })).toBeVisible();
      if (i === 1) {
        await page.getByRole('button', { name: 'Explore reference views', exact: true }).click();
        await page.getByRole('link', { name: 'Search pipeline', exact: true }).click();
        await page.getByText('Reason through failure cases', { exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Reranking never returns the expected product.' })).toBeVisible();
        await page.getByRole('link', { name: 'Return to Lab 2 in Workbench', exact: true }).click();
        await expect(page).toHaveURL(/lab=retrieval-acceptance/);
      }
      await page.getByRole('navigation', { name: 'Pellier Observatory views' }).getByRole('link', { name: 'Lab Collection' }).click();
    }
    await page.locator('[data-lab="04"]').getByRole('link', { name: 'Inspect lab evidence' }).click();
    await expect(page).toHaveURL(/\/observatory\/govern\/verification$/);
    await expect(page.getByRole('heading', { name: 'Which control acted?' })).toBeVisible();
    await expect(page.getByText('Sign in with an Operator account to inspect cross-principal evidence.')).toBeVisible();
    await page.getByRole('navigation', { name: 'Pellier surfaces' }).getByRole('link', { name: 'Storefront', exact: true }).click();
    await expect(page.getByRole('link', { name: 'Pellier home', exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('fonts and Cedar identity are self-hosted', async ({ page }) => {
    const thirdPartyAssets: string[] = [];
    page.on('request', request => {
      const host = new URL(request.url()).hostname;
      if (['fonts.gstatic.com', 'fonts.googleapis.com', 'cedarpolicy.com'].includes(host)) thirdPartyAssets.push(request.url());
    });
    await page.goto(`${BASE_URL}/observatory/govern/policies`);
    const cedar = page.getByRole('link', { name: 'Cedar policy language (opens in a new tab)' });
    await expect(cedar).toHaveAttribute('href', 'https://cedarpolicy.com/en');
    const mark = cedar.getByRole('img', { name: 'Cedar', exact: true });
    await expect(mark).toBeVisible();
    await expect.poll(() => mark.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true);
    expect(thirdPartyAssets).toEqual([]);
  });

  test('legacy lab URLs land on the corresponding workbench, without duplicated guides', async ({ page }) => {
    for (const lab of LABS) {
      await page.goto(`${BASE_URL}/observatory/labs/${lab}#steps-and-checkpoints`);
      await expect(page).toHaveURL(new RegExp(`/observatory/workbench\\?lab=${lab}`));
      await expect(page.getByRole('heading', { name: 'Workbench', exact: true })).toBeVisible();
      await expect(page.locator('.lab-guide')).toHaveCount(0);
    }
  });

  test('a signed-out Operator route requests identity and preserves the destination', async ({ page }) => {
    await page.goto(`${BASE_URL}/operator/clients/CUST-JESSICA?guided=service-recovery`);
    await expect(page.getByTestId('operator-sign-in')).toBeVisible();
    await page.getByTestId('operator-sign-in').click();
    await expect(page.getByTestId('pellier-signin')).toBeVisible();
    await expect(page).toHaveURL(/returnTo=.*operator/);
    await expect(page.getByTestId('operator-record')).toHaveCount(0);
    const protectedRead = await page.request.get(`${BASE_URL}/api/observatory/governance/outcomes`);
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
      for (const route of ['/', '/about', '/storyboard', '/product/2', '/how-pellier-works', '/observatory', '/observatory/workbench',
        '/observatory/govern', '/observatory/govern/authentication', '/observatory/govern/permissions',
        '/observatory/govern/agent-access', '/observatory/govern/policies', '/observatory/govern/actions',
        '/observatory/govern/verification', '/observatory/search', '/observatory/performance',
        '/observatory/tools', '/observatory/memory', '/observatory/architecture',
        '/observatory/evaluations', '/observatory/production-patterns', '/observatory/sessions', '/observatory/proof-board']) {
        await page.goto(`${BASE_URL}${route}`);
        await expect(page.getByRole('heading', { level: 1 }).first(), route).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), route).toBe(true);
      }
      expect(errors).toEqual([]);
    });
  }
});
