/**
 * E2E: happy-path email/password sign-in against the dedicated Cognito dev pool.
 *
 * Design contract: `.kiro/specs/pellier-storefront/design.md` — Testing
 * Strategy, "E2E (Playwright against a dedicated Cognito dev pool)". The
 * spec covers:
 *
 *   1. Open `/signin`
 *   2. Click the "Continue with email" CTA
 *   3. Fill the bootstrapped credentials from env vars
 *   4. Assert redirect back to home (`/`)
 *
 * Google and Apple IdP flows are validated via manual workshop dry-runs,
 * not here.
 *
 * Env vars (populated by the CI workflow from GitHub Actions secrets after
 * `bootstrap_cognito_dev_pool.py` runs):
 *
 *   - `E2E_TEST_USER_EMAIL`
 *   - `E2E_TEST_USER_PASSWORD`
 *   - `E2E_BASE_URL` (optional, defaults to http://localhost:5173)
 *
 * This is a placeholder implementation. Full flow coverage (preferences
 * modal, curated banner, grid re-sort) lands alongside the storefront
 * frontend work in Layer 4 / Layer 5 tasks.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

test.describe('auth happy path', () => {
  test('sign-in loop', async ({ page }) => {
    const email = process.env.E2E_TEST_USER_EMAIL;
    const password = process.env.E2E_TEST_USER_PASSWORD;

    test.skip(
      !email || !password,
      'E2E_TEST_USER_EMAIL / E2E_TEST_USER_PASSWORD not set — run ' +
        'tests/e2e/bootstrap_cognito_dev_pool.py first.',
    );

    // 1. Open /signin. AuthModal is the entry point; in the SPA the
    //    direct `/signin` route is wired by Task 4.x.
    await page.goto(`${BASE_URL}/signin`);

    // 2. Click the email CTA. Cognito Hosted UI opens; the email path
    //    does not carry an `identity_provider` query param.
    await page.getByRole('button', { name: /continue with email/i }).click();

    // 3. Fill credentials on the hosted UI. Selectors are Cognito's
    //    default email/password form; if the pool customizes its UI,
    //    update the locators here.
    await page.getByLabel(/email|username/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page
      .getByRole('button', { name: /sign in|log in|continue/i })
      .click();

    // 4. Callback completes and the SPA redirects to `/`. The Account
    //    button now reads "Hi, {givenName}" once `/api/auth/me` resolves.
    await expect(page).toHaveURL(new RegExp(`^${BASE_URL}/?($|\\?)`));
    await expect(page.getByRole('button', { name: /hi,/i })).toBeVisible({
      timeout: 15_000,
    });
  });
});
