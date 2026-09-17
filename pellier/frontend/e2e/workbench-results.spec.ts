import { expect, test, type Page } from '@playwright/test';
import type { EvidenceLedger, EvidenceLedgerEvent } from '../src/shared/evidenceLedger';

// Deterministic browser coverage of the real UI and SSE parser. Every API
// request is intercepted, so these scenarios never execute workshop actions.
test.use({ reducedMotion: 'reduce' });

const route = '/observatory/workbench?lab=grounded-inventory';
const prompt = 'Inspect the current warehouse stock.';
const persona = {
  id: 'marco', display_name: 'Marco', customer_id: 'CUST-MARCO',
  role_tag: 'Shopper', avatar_color: '#773d4c', avatar_initial: 'M',
  membership: 'gold', hero_image: '', hero_alt: '', hero_subheadline: '',
  stats: { visits: 1, orders: 1, last_seen_days: 1 },
};

function event(overrides: Partial<EvidenceLedgerEvent> = {}): EvidenceLedgerEvent {
  return {
    sequence: 1, eventKind: 'aurora', phase: 'execution', status: 'succeeded',
    provenance: 'aurora-receipt', turnId: 'browser-turn',
    evidenceRef: { kind: 'sql_query_log', id: '1' },
    title: 'Warehouse receipt', summary: 'One warehouse row returned.',
    sql: 'SELECT quantity FROM pellier.warehouse_inventory WHERE product_id = $1',
    details: { row_count: 1, execution_outcome: 'success' },
    ...overrides,
  };
}

function ledger(events: EvidenceLedgerEvent[] = []): EvidenceLedger {
  return {
    version: '1', authority: 'canonical-receipt-projection',
    principalScoped: true, turnId: 'browser-turn', events, evidenceSufficiency: [],
  };
}

function sse(events: object[]): string {
  return events.map(value => `data: ${JSON.stringify(value)}\n\n`).join('');
}

function complete(receipt: EvidenceLedger | null = ledger([event()])): string {
  return sse([
    { type: 'turn_start', turn_id: 'browser-turn' },
    { type: 'complete', response: {
      response: 'The recorded warehouse result is ready to inspect.',
      products: [], rail: 'in-process', evidence_ledger: receipt ?? undefined,
    } },
  ]);
}

async function fixture(
  page: Page,
  options: { body?: string; status?: number; receipt?: EvidenceLedger | null; hold?: Promise<void> } = {},
) {
  const calls: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem('pellier-session-id', 'browser-fixture-session');
  });
  await page.route('**/api/**', async request => {
    const path = new URL(request.request().url()).pathname;
    calls.push(`${request.request().method()} ${path}`);
    if (path === '/api/chat/stream') {
      await options.hold;
      await request.fulfill({
        status: options.status ?? 200,
        contentType: options.status ? 'application/json' : 'text/event-stream',
        body: options.body ?? complete(),
      });
    } else if (path === '/api/observatory/turns/browser-turn/ledger') {
      await request.fulfill({
        status: options.receipt ? 200 : 503,
        json: options.receipt ?? { detail: 'evidence_ledger_unavailable' },
      });
    } else if (path === '/api/persona/current') {
      await request.fulfill({ json: { persona } });
    } else if (path === '/api/observatory/scenarios') {
      await request.fulfill({ json: { persona: 'marco', scenarios: [{
        id: 1, ordinal: 1, prompt, journeyRole: 'required',
        journeyStage: 'establish', productName: null, imageUrl: null,
      }] } });
    } else if (path === '/api/health') {
      await request.fulfill({ json: { status: 'healthy' } });
    } else if (path.startsWith('/api/auth/')) {
      await request.fulfill({ status: 401, json: { detail: 'authentication_required' } });
    } else {
      await request.fulfill({ status: 404, json: { detail: 'Not part of this browser fixture' } });
    }
  });
  return calls;
}

async function run(page: Page) {
  await page.getByRole('button', { name: `Inspect: ${prompt}` }).click();
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
}

async function settlePanels(page: Page) {
  await page.waitForFunction(() => Array.from(document.querySelectorAll('[data-motion-panel]'))
    .every(panel => getComputedStyle(panel).opacity === '1'));
  await page.evaluate(() => document.fonts.ready);
}

for (const width of [1440, 1024, 768, 390]) {
  test(`idle and Operator handoff remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 810 });
    await fixture(page);
    await page.goto(route);
    if (width <= 1100) await page.getByRole('button', { name: 'Reconcile answer', exact: true }).click();
    await expect(page.getByText('Choose a shopper turn to inspect its answer and evidence.')).toBeVisible();
    if (width <= 1100) await page.getByRole('button', { name: 'Inspect evidence', exact: true }).click();
    await expect(page.getByRole('status', { name: 'Run proof summary' })).toHaveCount(1);
    await expect(page.getByRole('list', { name: 'Evidence categories' }).locator('li')).toHaveCount(7);
    await expect(page.locator('.observatory-products-empty, .observatory-answer-state')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Evidence sufficiency' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^Lab 1:/ })).toBeVisible();
    await noOverflow(page);
    if (width === 1440 || width === 390) {
      await settlePanels(page);
      await page.screenshot({ path: `/tmp/pellier-playwright/workbench-final-idle-${width}.png`, fullPage: true });
    }
    await page.getByRole('link', { name: /^Lab 4 Jessica:/ }).click();
    await expect(page.getByRole('link', { name: /Open Jessica in Operator/ })).toBeVisible();
    await expect(page.getByRole('status', { name: 'Run proof summary' })).toHaveCount(0);
    await expect(page.getByText('Choose a shopper turn to inspect its answer and evidence.')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Review the Lab 4 proof' })).toBeVisible();
    await noOverflow(page);
  });
}

test('receipt labels describe evaluation, empty results, and execution failures', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 810 });
  await fixture(page, { body: complete(ledger([
    event(),
    event({ sequence: 2, eventKind: 'policy', status: 'not_enforced', sql: null,
      title: 'Ownership evaluation', details: { decision: 'WOULD_DENY' } }),
    event({ sequence: 3, eventKind: 'retrieval', status: 'unavailable', sql: null,
      title: 'Empty retrieval', details: { citation_ids: [] } }),
    event({ sequence: 4, status: 'failed', title: 'Timed-out query',
      details: { execution_outcome: 'timeout' } }),
  ])) });
  await page.goto(route);
  await run(page);
  for (const label of ['Would deny (not enforced)', 'No citations returned', 'Query execution failed']) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(page.getByText('Evidence lookup failed', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toHaveCount(1);
  await noOverflow(page);
  await settlePanels(page);
  await page.screenshot({ path: '/tmp/pellier-playwright/workbench-final-evidence-1440.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow(page);
});

for (const status of [401, 503]) {
  test(`HTTP ${status} cannot masquerade as a verified empty result`, async ({ page }) => {
    await fixture(page, { status, body: JSON.stringify({ detail: 'Request unavailable' }) });
    await page.goto(route);
    await run(page);
    await expect(page.getByText(/Linked claims are unavailable/)).toBeVisible();
    await expect(page.getByText('This turn linked no claim to an emitted event.')).toHaveCount(0);
    await expect(page.getByRole('list', { name: 'Evidence categories' })).toHaveCount(0);
    if (status === 401) {
      await expect(page.getByRole('link', { name: 'Sign in to continue' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Retry turn' })).toHaveCount(0);
      await expect(page.getByText('Denied', { exact: true })).toHaveCount(0);
    }
  });
}

for (const readable of [true, false]) {
  test(`a streamed denial reads the exact ledger without replay (available: ${readable})`, async ({ page }) => {
    const calls = await fixture(page, {
      body: sse([
        { type: 'turn_start', turn_id: 'browser-turn' },
        { type: 'error', code: 'policy_denied', retryable: false, message: 'The ownership policy denied this request.' },
      ]),
      receipt: readable ? ledger([event({ eventKind: 'policy', status: 'denied', sql: null, title: 'Ownership denied' })]) : null,
    });
    await page.goto(route);
    await run(page);
    await expect(page.getByRole('alert')).toContainText('Policy denied');
    await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Denied');
    await expect(page.getByText(readable
      ? 'This turn linked no claim to an emitted event.'
      : 'Linked claims are unavailable because no durable ledger was received for this turn.',
    )).toBeVisible();
    expect(calls.filter(call => call.includes('/api/chat/stream'))).toHaveLength(1);
    expect(calls.filter(call => call.includes('/turns/browser-turn/ledger'))).toEqual([
      'GET /api/observatory/turns/browser-turn/ledger',
    ]);
    await expect(page.getByRole('button', { name: 'Retry turn' })).toHaveCount(0);
  });
}

test('Resume, history, and Open event reveal the destination panel on a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await fixture(page);
  await page.addInitScript(() => localStorage.setItem('pellier-lab-progress', JSON.stringify({
    lab: 'grounded-inventory', step: 'inspect', nextAction: '', updatedAt: '2026-09-17T00:00:00Z',
  })));
  await page.goto(`${route}&step=inspect`);
  await page.getByRole('button', { name: 'Reconcile answer', exact: true }).click();
  await expect(page).toHaveURL(/step=reconcile/);
  await page.getByRole('link', { name: /^Resume/ }).click();
  await expect(page.getByRole('button', { name: 'Inspect evidence', exact: true })).toHaveAttribute('aria-current', 'step');
  await page.goBack();
  await expect(page.getByRole('button', { name: 'Reconcile answer', exact: true })).toHaveAttribute('aria-current', 'step');
  await page.goForward();
  await expect(page.getByRole('button', { name: 'Inspect evidence', exact: true })).toHaveAttribute('aria-current', 'step');
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await run(page);
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Completed');
  await page.getByRole('button', { name: 'Reconcile answer', exact: true }).click();
  await page.getByRole('button', { name: 'Open event', exact: true }).click();
  await expect(page).toHaveURL(/step=inspect/);
  await expect(page.locator('[data-linked="true"]')).toBeVisible();
});

test('running and verified-empty states are distinct, and a late run cannot enter another lab', async ({ page }) => {
  let release!: () => void;
  const hold = new Promise<void>(resolve => { release = resolve; });
  await fixture(page, { hold, body: complete(ledger()) });
  await page.goto(route);
  await run(page);
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Running');
  await expect(page.getByRole('heading', { name: 'Evidence sufficiency' })).toHaveCount(0);
  release();
  await expect(page.getByText('The recorded ledger contains no events for this turn.')).toBeVisible();
  await expect(page.getByText('This turn linked no claim to an emitted event.')).toBeVisible();

  let finish!: () => void;
  const late = new Promise<void>(resolve => { finish = resolve; });
  await page.route('**/api/chat/stream', async request => {
    await late;
    await request.fulfill({ contentType: 'text/event-stream', body: complete() });
  });
  await run(page);
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Running');
  await page.getByRole('link', { name: /^Lab 2 Anna:/ }).click();
  const response = page.waitForResponse('**/api/chat/stream');
  finish();
  await response;
  await expect(page.getByRole('heading', { name: /^Lab 2:/ })).toBeVisible();
  await expect(page.getByRole('status', { name: 'Run proof summary' })).toContainText('Ready');
  await expect(page.getByText('The recorded warehouse result is ready to inspect.')).toHaveCount(0);
});
