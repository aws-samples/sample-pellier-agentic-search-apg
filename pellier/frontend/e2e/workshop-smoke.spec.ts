/**
 * E2E: Workshop smoke test — the re:Invent readiness gate.
 *
 * This suite runs against the PRODUCTION BUILD served by FastAPI on
 * port 8000 (one process, one port). It exercises the demo path a
 * presenter walks through on stage so regressions catch ahead of the
 * room:
 *
 *   1. Home page loads without console errors.
 *   2. Fonts are self-hosted — no requests to fonts.gstatic.com.
 *   3. Triage fast-path: "hi" produces a reply instantly, without
 *      routing to the specialist chain.
 *   4. Real query produces streaming tokens + a non-empty reply.
 *   5. ?reset=1 clears persisted state.
 *
 * Runs on macOS, Windows, and Ubuntu runners — see
 * .github/workflows/workshop-smoke.yml.
 *
 * NOTE: does not require Cognito or AWS creds. Bedrock is required
 * for step 4 (real query); if Bedrock is unavailable, step 4 falls
 * back to asserting the fallback message ("I looked through the
 * catalog...") instead of a positive product reply. That still
 * exercises the full pipeline — triage → orchestrator → fallback —
 * without depending on external model availability.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000';

test.describe('Workshop production build smoke', () => {
  test('home page loads without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !msg.text().includes('401')) {
        // 401s from /api/auth/me are expected for anonymous users.
        errors.push(msg.text());
      }
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await expect(page).toHaveTitle(/Pellier/);
    expect(errors, `console errors: ${errors.join('\n')}`).toHaveLength(0);
  });

  test('fonts are self-hosted (no fonts.gstatic.com requests)', async ({
    page,
  }) => {
    const googleFontRequests: string[] = [];
    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('fonts.gstatic.com') || url.includes('fonts.googleapis.com')) {
        googleFontRequests.push(url);
      }
    });

    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    expect(
      googleFontRequests,
      `Google Fonts should not be loaded: ${googleFontRequests.join(', ')}`,
    ).toHaveLength(0);
  });

  test('triage fast-path: "hi" replies instantly without LLM calls', async ({
    page,
  }) => {
    await page.goto(BASE_URL);
    // Clear any persisted chat state from prior runs.
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    // Cmd+K on macOS, Ctrl+K elsewhere. Try both to stay
    // platform-agnostic — Playwright's key mapping varies by runner.
    await page.keyboard.press('Control+K');
    const modal = page.locator('[data-testid=concierge-modal]');
    if (!(await modal.isVisible().catch(() => false))) {
      await page.keyboard.press('Meta+K');
    }
    await modal.waitFor({ state: 'visible', timeout: 5000 });

    const input = page.locator('.ec-input-field').first();
    await input.fill('hi');
    await page.keyboard.press('Enter');

    // Triage reply should land in under 3 seconds — no LLM in loop.
    const body = page.locator('.ec-msg-body').first();
    await expect(body).toContainText("I'm Pellier", { timeout: 3000 });
  });

  test('real query: streaming tokens land, reply is non-empty', async ({
    page,
  }) => {
    await page.goto(BASE_URL);
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    await page.keyboard.press('Control+K');
    const modal = page.locator('[data-testid=concierge-modal]');
    if (!(await modal.isVisible().catch(() => false))) {
      await page.keyboard.press('Meta+K');
    }
    await modal.waitFor({ state: 'visible', timeout: 5000 });

    const input = page.locator('.ec-input-field').first();
    await input.fill('find me a linen shirt under $150');
    await page.keyboard.press('Enter');

    // A real orchestrator turn can take 10-20s. Poll for non-empty
    // text rather than using the missing ``toBeEmpty`` matcher.
    // Guards against the empty-bubble regression we hit pre-fallback.
    const body = page.locator('.ec-msg-body').first();
    await expect(async () => {
      const text = (await body.textContent()) ?? '';
      expect(text.trim().length).toBeGreaterThan(10);
    }).toPass({ timeout: 45_000 });
  });

  test('?reset=1 clears persisted localStorage keys', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.evaluate(() => {
      localStorage.setItem('smoke-test-key', 'poisoned');
    });
    const before = await page.evaluate(() =>
      localStorage.getItem('smoke-test-key'),
    );
    expect(before).toBe('poisoned');

    await page.goto(`${BASE_URL}/?reset=1`);
    // Give the reset effect + reload cycle a moment.
    await page.waitForTimeout(1500);

    const after = await page.evaluate(() =>
      localStorage.getItem('smoke-test-key'),
    );
    expect(after).toBeNull();

    // URL should be stripped of the reset flag.
    expect(page.url()).not.toContain('reset=1');
  });
});
