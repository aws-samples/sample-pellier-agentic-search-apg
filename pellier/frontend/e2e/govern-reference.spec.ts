import { expect, test } from '@playwright/test';

// This file includes real sign-in. Never persist credential-bearing traces,
// video, or automatic failure screenshots. Layout shots are explicit below.
test.use({ trace: 'off', screenshot: 'off', video: 'off' });

const topics = [
  ['authentication', 'Authentication & JWTs'],
  ['permissions', 'Roles & permissions'],
  ['agent-access', 'Agent Access'],
  ['policies', 'Cedar policies'],
  ['actions', 'Governed actions'],
  ['verification', 'Evidence & verification'],
] as const;

test.describe('Govern connected reference', () => {
  test('all topics are discoverable, keyboard reachable, and free of runtime errors', async ({ page }) => {
    const errors: string[] = [];
    const toolCalls: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error' && !message.text().includes('401') && !message.text().includes('403')) errors.push(message.text());
    });
    page.on('request', request => {
      if (request.method() === 'POST' && /\/(chat|execute|tool-call)(?:\/|\?|$)/.test(request.url())) toolCalls.push(request.url());
    });
    await page.goto('/observatory');
    await page.getByRole('navigation', { name: 'Pellier Observatory views' }).getByRole('link', { name: 'Govern', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Governed agent access');
    await expect(page).toHaveTitle('Govern · Pellier Observatory');
    for (const [slug, label] of topics) {
      await page.getByRole('navigation', { name: 'Govern topics' }).getByRole('link', { name: label, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/observatory/govern/${slug}$`));
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(label);
      await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
      await expect(page.locator('vite-error-overlay')).toHaveCount(0);
      if (slug === 'agent-access') {
        const operator = page.getByRole('row').filter({ hasText: 'Operator investigation and action' });
        await expect(operator).toContainText('separate IAM-authenticated AgentCore Runtime');
        await expect(operator).toContainText('Operator’s token through Gateway');
        await expect(operator).toContainText('A managed failure does not fall back to local execution.');
      }
    }
    const boundaryEvidence = page.getByRole('region', { name: 'Which control acted?' });
    await expect(boundaryEvidence.getByRole('alert')).toContainText('Sign in with an Operator account');
    await expect(boundaryEvidence.getByRole('link', { name: 'Sign in as Operator' }))
      .toHaveAttribute('href', '/signin?workspace=operator&returnTo=%2Fobservatory%2Fgovern%2Fverification');
    await expect(boundaryEvidence.getByText('Not yet proved', { exact: true })).toHaveCount(0);
    const authenticationLink = page.getByRole('navigation', { name: 'Govern topics' }).getByRole('link', { name: 'Authentication & JWTs', exact: true });
    await authenticationLink.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Authentication & JWTs');
    await expect(page.getByRole('navigation', { name: 'Govern topics' }).getByRole('link', { name: 'Authentication & JWTs', exact: true })).toHaveAttribute('aria-current', 'page');
    expect(toolCalls).toEqual([]);
    expect(errors).toEqual([]);
  });

  test('legacy Write path opens actual policy definitions with observed modes', async ({ page }) => {
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/observatory/governance/policies'));
    await page.goto('/observatory/write-path');
    await expect(page).toHaveURL(/\/observatory\/govern\/policies$/);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect(response.headers()['cache-control']).toBe('no-store');
    const snapshot = await response.json();
    expect(snapshot.source).toBe('managed-engine');
    expect(snapshot.policies.length).toBeGreaterThan(0);
    const observation = page.getByRole('region', { name: 'Observed Gateway and policy configuration' });
    await expect(observation.getByText(snapshot.gatewayMode, { exact: true })).toBeVisible();
    const policy = snapshot.policies.find((item: { cedar?: string }) => item.cedar);
    await page.getByRole('searchbox').fill(policy.name);
    const details = page.locator('details.govern-policy').filter({ hasText: policy.name }).first();
    await details.locator('summary').click();
    await expect(details.locator('pre')).toHaveText(policy.cedar);
    await page.getByRole('searchbox').fill('intentionally-no-policy-match');
    await expect(observation.getByRole('status')).toHaveText('0 matching policies');
    await expect(page.locator('details.govern-policy')).toHaveCount(0);
  });

  test('a failed refresh removes the previous configuration', async ({ page }) => {
    await page.goto('/observatory/govern/policies');
    const observation = page.getByRole('region', { name: 'Observed Gateway and policy configuration' });
    await expect(observation.getByText(/definitions just read/)).toBeAttached({ timeout: 25_000 });
    await page.route('**/api/observatory/governance/policies', route => route.fulfill({
      status: 503, contentType: 'application/json', body: '{"detail":"policy_snapshot_unavailable"}',
    }));
    await page.getByRole('button', { name: 'Refresh policies' }).click();
    await expect(observation.getByText(/The policy snapshot is unavailable/)).toBeVisible();
    await expect(observation.locator('.govern-facts')).toHaveCount(0);
    await expect(observation.locator('details.govern-policy')).toHaveCount(0);
  });

  for (const width of [1440, 1024, 768, 390]) {
    test(`layout and policy disclosure at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      for (const path of ['/observatory/govern', '/observatory/govern/policies', '/observatory/govern/permissions']) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        expect(overflow, `${path} should not overflow the viewport`).toBe(false);
        if (width === 390) {
          await expect(page.getByRole('navigation', { name: 'Govern topics' })).toBeHidden();
          await page.getByRole('button', { name: 'Browse Govern topics' }).click();
        }
        await expect(page.getByRole('navigation', { name: 'Govern topics' })).toBeVisible();
        if (path.endsWith('/policies')) {
          await expect(page.locator('details.govern-policy').first()).toBeVisible({ timeout: 25_000 });
          await page.locator('details.govern-policy').first().locator('summary').click();
          await expect(page.locator('details.govern-policy').first().locator('pre')).toBeVisible();
          expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)).toBe(false);
          if (width >= 768) {
            await page.evaluate(() => window.scrollTo({ top: 600, behavior: 'instant' }));
            const { sidebarTop, headerBottom } = await page.evaluate(() => ({
              sidebarTop: document.querySelector('.govern-sidebar')!.getBoundingClientRect().top,
              headerBottom: document.querySelector('.observatory-topbar')!.getBoundingClientRect().bottom,
            }));
            expect(sidebarTop, 'Topic navigation stays below the sticky application headers').toBeGreaterThanOrEqual(headerBottom);
          }
          if (width === 1440 || width === 390) {
            await page.evaluate(() => document.fonts.ready);
            await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
            await page.screenshot({ path: `/tmp/pellier-govern-policies-${width}.png`, fullPage: true, animations: 'disabled' });
          }
        }
      }
      await page.goto('/observatory/govern');
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Governed agent access');
      if (width === 390) {
        await expect(page.getByRole('navigation', { name: 'Govern topics' })).toBeHidden();
        await page.getByRole('button', { name: 'Browse Govern topics' }).click();
      }
      await expect(page.getByRole('navigation', { name: 'Govern topics' })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await expect(page.getByRole('link', { name: 'Skip to content' })).not.toBeInViewport();
      await page.screenshot({ path: `/tmp/pellier-govern-${width}.png`, fullPage: true, animations: 'disabled' });
    });
  }
});

test.describe('Govern real Cognito sign-in', () => {
  test('sign-in returns to the validated caller panel and shopper authority stays scoped', async ({ page }) => {
    const username = process.env.E2E_GOVERN_USERNAME;
    const password = process.env.E2E_GOVERN_PASSWORD;
    test.skip(!username || !password, 'Requires the existing workshop test identity, supplied only in process memory.');
    await page.goto('/observatory/govern/authentication');
    await page.getByRole('link', { name: 'Sign in to inspect your identity' }).click();
    await page.getByLabel('Username', { exact: true }).fill(username!);
    await page.getByLabel('Password', { exact: true }).fill(password!);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/observatory\/govern\/authentication$/, { timeout: 30_000 });
    await expect(page.getByText('Validated access token', { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('region', { name: 'Current caller observation' }).getByText('Not a member', { exact: true })).toBeVisible();
    await page.getByRole('navigation', { name: 'Govern topics' }).getByRole('link', { name: 'Evidence & verification' }).click();
    await expect(page.getByRole('region', { name: 'Which control acted?' }).getByRole('alert'))
      .toContainText('Sign in with an Operator account');
    await page.getByText('Inspect the return and RLS subset', { exact: true }).click();
    await expect(page.getByText(/Shopper sign-in alone does not grant access/)).toBeVisible();
  });
});
