/**
 * E2E: silent token refresh on a 401.
 *
 * Design contract: `.kiro/specs/pellier-storefront/design.md` —
 * Testing Strategy, "E2E (Playwright against a dedicated Cognito dev
 * pool)". Exercises Requirement 5.3 (cookie-based auth) and Task 5.1's
 * 401 interceptor contract:
 *
 *   1. Sign in once against the dev pool (same bootstrapped credentials
 *      as `auth-happy-path.spec.ts`).
 *   2. Expire the `access_token` cookie while leaving the
 *      `refresh_token` cookie intact.
 *   3. Trigger any authenticated request (e.g. `/api/auth/me`) and
 *      assert that the SPA silently refreshes via `/api/auth/refresh`
 *      and the original request retries successfully - the user stays
 *      on the page with no redirect to `/signin`.
 *
 * Env vars (populated by `bootstrap_cognito_dev_pool.py` in CI):
 *
 *   - `E2E_TEST_USER_EMAIL`
 *   - `E2E_TEST_USER_PASSWORD`
 *   - `E2E_BASE_URL` (optional, defaults to http://localhost:5173)
 *
 * Test pattern: perform a real sign-in, then manipulate only the
 * `access_token` cookie via `context.clearCookies({ name: 'access_token' })`
 * to simulate expiry. The refresh cookie remains, so the SPA interceptor
 * from Task 5.1 should kick in on the next 401. We assert via network
 * events (request to `/api/auth/refresh` happened, retry of the original
 * 401'd request returned 200) rather than DOM state alone so the test is
 * robust to UI churn.
 *
 * This is a scaffolding spec. It guards the full stack needs to be up
 * (backend + frontend + Cognito dev pool) with env vars set; otherwise
 * it skips. Nightly CI runs against a live dev pool per Task 7.3.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';

test.describe('auth refresh', () => {
  test('silent refresh on expired access token retries the original request', async ({
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

    // 1. Sign in with the bootstrapped credentials. Mirrors the happy
    //    path spec so the refresh test starts from a known-good state.
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

    // 2. Expire ONLY the access_token cookie. Leave refresh_token so the
    //    SPA's /api/auth/refresh call (Task 5.1) can rotate tokens.
    const cookies = await context.cookies();
    const refreshCookie = cookies.find((c) => c.name === 'refresh_token');
    expect(
      refreshCookie,
      'refresh_token cookie missing after sign-in; auth wiring regression',
    ).toBeDefined();

    await context.clearCookies({ name: 'access_token' });

    // 3. Track the refresh + retry network dance. The 401 interceptor from
    //    Task 5.1 should POST /api/auth/refresh and then retry the
    //    original authenticated request exactly once.
    const refreshRequest = page.waitForRequest((req) =>
      req.url().endsWith('/api/auth/refresh') && req.method() === 'POST',
    );
    const meRetry = page.waitForResponse((res) =>
      res.url().endsWith('/api/auth/me') && res.status() === 200,
    );

    // Trigger an authenticated fetch. Reloading the page is the simplest
    // way to fire `/api/auth/me` via the AuthProvider bootstrap.
    await page.reload();

    await refreshRequest;
    await meRetry;

    // The SPA must stay on the current page - no redirect to /signin.
    await expect(page).toHaveURL(new RegExp(`^${BASE_URL}/?($|\\?)`));
    await expect(page.getByRole('button', { name: /hi,/i })).toBeVisible({
      timeout: 10_000,
    });
  });
});
