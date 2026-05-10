/**
 * E2E: anonymous browsing, sign in, confirm personalized grid re-renders.
 *
 * Design contract: `.kiro/specs/pellier-storefront/design.md` -
 * Testing Strategy, "E2E (Playwright against a dedicated Cognito dev
 * pool)". Exercises Requirements 1.6.6 (grid remount on prefsVersion),
 * 3.3.1-3.3.5 (personalized products), 4.3.3 (anon namespace isolation).
 *
 * Flow:
 *   1. Visit the storefront anonymously. Sign-in strip is visible, the
 *      grid renders in default editorial order, and the Account button
 *      reads "Account".
 *   2. Capture the anonymous grid order (the 9 showcase products, by
 *      name).
 *   3. Sign in via the email CTA with the bootstrapped credentials.
 *   4. If the preferences modal auto-opens (first sign-in on this pool),
 *      pick a distinctive preference set so the re-sort is observable
 *      (e.g. `Creative` vibe, `Evenings out` occasion, `Dresses`
 *      category) so Sundress + Cardigan bubble up per Task 3.6.
 *   5. Assert the grid re-renders in a different order than the
 *      anonymous snapshot and the Account button now reads "Hi, ...".
 *   6. Confirm no anon chat history leaked into the authenticated
 *      session (Req 4.3.3) - the concierge opens fresh with no prior
 *      turns.
 *
 * Env vars (populated by `bootstrap_cognito_dev_pool.py` in CI):
 *
 *   - `E2E_TEST_USER_EMAIL`
 *   - `E2E_TEST_USER_PASSWORD`
 *   - `E2E_BASE_URL` (optional, defaults to http://localhost:5173)
 *
 * Test pattern: work from the outside in via visible DOM + the Account
 * button label to avoid coupling to component internals. Capture grid
 * order by reading `data-testid="product-card-name"` nodes; the
 * `ProductCard` from Task 4.6 exposes a stable hook for this.
 *
 * This is a scaffolding spec. It requires the full stack + Cognito dev
 * pool + env vars; otherwise it skips. Nightly CI runs this green per
 * Task 7.3.
 */

import { expect, test, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

async function readGridOrder(page: Page): Promise<string[]> {
  const names = page.locator('[data-testid="product-card-name"]');
  await expect(names.first()).toBeVisible({ timeout: 10_000 });
  return names.allTextContents();
}

test.describe('anon to auth', () => {
  test('signing in from anonymous state re-sorts the personalized grid', async ({
    page,
  }) => {
    const email = process.env.E2E_TEST_USER_EMAIL;
    const password = process.env.E2E_TEST_USER_PASSWORD;

    test.skip(
      !email || !password,
      'E2E_TEST_USER_EMAIL / E2E_TEST_USER_PASSWORD not set - run ' +
        'tests/e2e/bootstrap_cognito_dev_pool.py first.',
    );

    // 1. Anonymous visit. Account button reads "Account", sign-in strip
    //    is visible, grid renders editorial default order.
    await page.goto(`${BASE_URL}/`);
    await expect(
      page.getByRole('button', { name: /^account$/i }),
    ).toBeVisible();

    // 2. Capture the anonymous grid order.
    const anonOrder = await readGridOrder(page);
    expect(anonOrder.length).toBeGreaterThanOrEqual(9);

    // 3. Sign in via the email CTA. Reuses the happy-path sequence.
    await page.goto(`${BASE_URL}/signin`);
    await page.getByRole('button', { name: /continue with email/i }).click();
    await page.getByLabel(/email|username/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page
      .getByRole('button', { name: /sign in|log in|continue/i })
      .click();
    await expect(page).toHaveURL(new RegExp(`^${BASE_URL}/?($|\\?)`));

    // 4. If the preferences modal auto-opens (Req 1.4 just_signed_in
    //    flow), pick a distinctive preference set. On repeat signs-in
    //    the modal is skipped; the test still asserts re-sort because
    //    personalized=true flips on as soon as prefs exist.
    const prefsHeader = page.getByText(/a quick tune-up/i);
    if (await prefsHeader.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await page.getByRole('button', { name: /^creative$/i }).click();
      await page.getByRole('button', { name: /^evenings out$/i }).click();
      await page.getByRole('button', { name: /^dresses$/i }).click();
      await page
        .getByRole('button', { name: /save and see my storefront/i })
        .click();
    }

    // 5. Account label flips to "Hi, ..." and grid re-renders.
    await expect(page.getByRole('button', { name: /hi,/i })).toBeVisible({
      timeout: 15_000,
    });

    // Grid remount is keyed on prefsVersion (Req 1.6.6); wait for the
    // new order to differ from the anonymous snapshot.
    await expect
      .poll(async () => (await readGridOrder(page)).join('|'), {
        timeout: 10_000,
      })
      .not.toBe(anonOrder.join('|'));

    // 6. Anon chat history does not leak into the authed session.
    //    Open the concierge and assert no prior turns are rendered.
    await page.getByTestId('command-pill').click();
    const conciergeHistory = page.locator(
      '[data-testid="concierge-history-turn"]',
    );
    await expect(conciergeHistory).toHaveCount(0);
  });
});
