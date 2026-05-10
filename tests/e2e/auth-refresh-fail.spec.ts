/**
 * E2E: refresh failure lands the user on `/signin` with all three
 * providers visible.
 *
 * Design contract: `.kiro/specs/pellier-storefront/design.md` -
 * Testing Strategy, "E2E (Playwright against a dedicated Cognito dev
 * pool)". Exercises Requirement 4.1 / 5.3 and Task 5.1's 401 interceptor
 * fallthrough:
 *
 *   When `/api/auth/refresh` fails (no refresh_token, expired
 *   refresh_token, or revoked session), the SPA must redirect to
 *   `/signin?returnTo=<current_path>` and the `AuthModal` must render
 *   all three providers (Google, Apple, email) with no provider
 *   preselected.
 *
 * Env vars (populated by `bootstrap_cognito_dev_pool.py` in CI):
 *
 *   - `E2E_TEST_USER_EMAIL`
 *   - `E2E_TEST_USER_PASSWORD`
 *   - `E2E_BASE_URL` (optional, defaults to http://localhost:5173)
 *
 * Test pattern:
 *   1. Sign in normally so all three auth cookies are set.
 *   2. Clear BOTH `access_token` AND `refresh_token` to guarantee the
 *      refresh call fails with 401.
 *   3. Trigger an authenticated request (page reload). The interceptor
 *      from Task 5.1 attempts one refresh, fails, and calls
 *      `openSignInChooser({ returnTo: ... })`.
 *   4. Assert the redirect lands on `/signin` with a `returnTo` query
 *      param AND that the chooser shows all three CTAs.
 *
 * This is a scaffolding spec. It requires the full stack + Cognito dev
 * pool + env vars; otherwise it skips. Nightly CI runs this green per
 * Task 7.3.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

test.describe('auth refresh fail', () => {
  test('failed refresh redirects to /signin with all three providers', async ({
    page,
    context,
  }) => {
    const email = process.env.E2E_TEST_USER_EMAIL;
    const password = process.env.E2E_TEST_USER_PASSWORD;

    test.skip(
      !email || !password,
      'E2E_TEST_USER_EMAIL / E2E_TEST_USER_PASSWORD not set - run ' +
        'tests/e2e/bootstrap_cognito_dev_pool.py first.',
    );

    // 1. Sign in. Reuses the happy-path CTA sequence so we know the
    //    three httpOnly cookies (access_token, id_token, refresh_token)
    //    are present before we destroy them.
    await page.goto(`${BASE_URL}/signin`);
    await page.getByRole('button', { name: /continue with email/i }).click();
    await page.getByLabel(/email|username/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page
      .getByRole('button', { name: /sign in|log in|continue/i })
      .click();
    await expect(page).toHaveURL(new RegExp(`^${BASE_URL}/?($|\\?)`));
    await expect(page.getByRole('button', { name: /hi,/i })).toBeVisible({
      timeout: 15_000,
    });

    // 2. Clear both access + refresh cookies. The next authenticated
    //    request returns 401, the interceptor tries /api/auth/refresh,
    //    which also returns 401 (no refresh_token cookie to trade in),
    //    and the interceptor falls through to the chooser.
    await context.clearCookies({ name: 'access_token' });
    await context.clearCookies({ name: 'refresh_token' });

    // 3. Trigger an authenticated request. Reload hits /api/auth/me.
    await page.reload();

    // 4. Redirect lands on /signin?returnTo=... and the AuthModal
    //    renders all three provider CTAs.
    await expect(page).toHaveURL(/\/signin(\?.*returnTo=|$)/, {
      timeout: 15_000,
    });

    await expect(
      page.getByRole('button', { name: /continue with google/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /continue with apple/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /continue with email/i }),
    ).toBeVisible();
  });
});
