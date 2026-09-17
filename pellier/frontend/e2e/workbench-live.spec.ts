import { expect, test } from '@playwright/test';
import { writeFile } from 'node:fs/promises';

// Credentials stay in process memory. Never record the sign-in surface or
// request bodies. Only the settled, seeded workshop result is screenshotted.
test.use({ trace: 'off', screenshot: 'off', video: 'off', reducedMotion: 'reduce' });

test('a signed-in shopper turn reconciles to a real principal-scoped ledger', async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  const username = process.env.E2E_GOVERN_USERNAME;
  const password = process.env.E2E_GOVERN_PASSWORD;
  test.skip(!username || !password, 'Requires the existing Marco workshop identity in process memory.');

  const workbench = '/observatory/workbench?lab=grounded-inventory';
  await page.goto(`/signin?returnTo=${encodeURIComponent(workbench)}`);
  await page.getByLabel('Username', { exact: true }).fill(username!);
  await page.getByLabel('Password', { exact: true }).fill(password!);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/observatory\/workbench\?lab=grounded-inventory$/, { timeout: 30_000 });

  const selected = await page.request.post('/api/persona/switch', {
    data: { persona_id: 'marco', current_session_id: null },
  });
  expect(selected.status()).toBe(200);
  const session = await selected.json();
  expect(session.persona.customer_id).toBe('CUST-MARCO');
  await page.evaluate(sessionId => {
    localStorage.setItem('pellier-session-id', sessionId);
  }, session.session_id);
  await page.reload();

  const response = page.waitForResponse('**/api/chat/stream');
  // Marco's first guided request is a catalogue read, with no return or write.
  await page.getByRole('button', { name: 'Inspect: What linen do you have for 10 days in Goa?' }).click();
  const stream = await response;
  expect(stream.status()).toBe(200);
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Completed', { timeout: 180_000 });
  await expect(page.getByRole('heading', { name: 'Evidence sufficiency' })).toBeVisible();
  await expect(page.locator('.observatory-trace-step').first()).toBeVisible();
  const records = (await stream.text()).split('\n')
    .filter(line => line.startsWith('data: '))
    .map(line => JSON.parse(line.slice(6)));
  const receipt = records.find(record => record.type === 'complete')?.response?.evidence_ledger;
  expect(receipt?.authority).toBe('canonical-receipt-projection');
  expect(receipt?.principalScoped).toBe(true);
  expect(receipt?.events.length).toBeGreaterThan(0);
  // Use the browser's same-origin cookie path, exactly as denial recovery does.
  // Playwright's separate HTTP client does not share Chrome's secure-cookie
  // exception for local loopback HTTP.
  const persisted = await page.evaluate(async (turnId) => {
    const response = await fetch(`/api/observatory/turns/${encodeURIComponent(turnId)}/ledger`, { credentials: 'include' });
    return { status: response.status, ledger: response.ok ? await response.json() : null };
  }, receipt.turnId);
  expect(persisted.status).toBe(200);
  const durable = persisted.ledger;
  expect(durable.turnId).toBe(receipt.turnId);
  expect(durable.principalScoped).toBe(true);
  expect(durable.events.length).toBeGreaterThan(0);
  const summary = JSON.stringify({
    observedAt: new Date().toISOString(),
    turnId: receipt.turnId, authority: receipt.authority,
    principalScoped: receipt.principalScoped, durableReadStatus: persisted.status,
    eventKinds: receipt.events.map((event: { eventKind: string }) => event.eventKind),
    sufficiencyChecks: receipt.evidenceSufficiency.length,
  }, null, 2);
  await testInfo.attach('live-evidence-summary', {
    contentType: 'application/json',
    body: summary,
  });
  await writeFile('/tmp/pellier-playwright/live-turn-summary.json', summary);
  await page.setViewportSize({ width: 1440, height: 810 });
  await page.screenshot({ path: '/tmp/pellier-playwright/workbench-final-live-1440.png', fullPage: true });
});
