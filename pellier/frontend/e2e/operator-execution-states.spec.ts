/**
 * The Operator's execution states in both themes: Jessica's record after an
 * investigation, the review after approval, a first Execute that Cedar
 * denies, Execute again that is allowed, and a replay with the same key.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 OPERATOR_SHOTS=/path/to/dir \
 *     npx playwright test e2e/operator-execution-states.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import {
  ANSWERED_REQUEST, APPROVED_REVIEW, BOOK, EXECUTED_REVIEW, INVESTIGATION_EVENTS, INVESTIGATION_TAIL,
  NADIA_ME, OPEN_REQUEST, PENDING_REVIEW, RECORD, RECORDED_ONCE, WRITE_KEY, detail, sse,
} from './fixtures/jessica-case'

const SHOTS = process.env.OPERATOR_SHOTS ?? 'test-results/operator-states'

const NOTHING_WRITTEN = {
  idempotencyKey: WRITE_KEY, creditRows: 0, creditIds: [], amountCents: null, auditRows: 0, auditIds: [],
  auditCaller: null, readable: true,
}

const DENIED_NOTE = 'The Gateway answered: denied, 2026-10-04 15:03 UTC. AgentCore Policy denied it before the tool ran (forbid policies naming this action just before the call: credit_limit_forbid). tool_audit and store_credits show what ran and what was paid.'

const DENIED_REVIEW = {
  ...EXECUTED_REVIEW,
  assurance: { human: 'CONFIRMED', policy: 'DENY', aurora: 'NOT_REACHED', evidence: 'NO_EXECUTION' },
  execution: {
    ...EXECUTED_REVIEW.execution, rail: null,
    notes: { policy: DENIED_NOTE },
    lastAttempt: {
      ...EXECUTED_REVIEW.execution.lastAttempt, outcome: 'denied', policy: 'DENY',
      label: 'The Gateway answered: denied', detail: 'Tool call not allowed due to policy enforcement',
    },
  },
}

interface Desk {
  review: Record<string, unknown>
  record: Record<string, unknown> | null
  investigated: boolean
  executions: number
}

function executeResult(desk: Desk) {
  const denied = desk.executions === 1
  return {
    reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-1', idempotencyKey: WRITE_KEY,
    actorPrincipal: 'sub-nadia',
    assurance: denied ? DENIED_REVIEW.assurance : EXECUTED_REVIEW.assurance,
    notes: { policy: denied ? DENIED_NOTE : EXECUTED_REVIEW.execution.notes.policy },
    tool: 'give_store_credit',
    result: denied
      ? { status: 'denied' }
      : { status: 'success', credit_id: 12, amount: '100.00', idempotent_replay: desk.executions > 2 },
    record: denied ? NOTHING_WRITTEN : RECORDED_ONCE,
  }
}

async function stubDesk(page: Page, desk: Desk) {
  const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/ports\/\d+/, '')
    const method = route.request().method()
    const request = desk.investigated ? ANSWERED_REQUEST : OPEN_REQUEST
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(NADIA_ME))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.endsWith('/api/operator/clients')) return route.fulfill(json(BOOK))
    if (path.endsWith('/api/operator/clients/CUST-JESSICA/investigate') && method === 'POST') {
      desk.investigated = true
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([...INVESTIGATION_EVENTS, ...INVESTIGATION_TAIL]) })
    }
    if (path.endsWith('/api/operator/clients/CUST-JESSICA')) {
      return route.fulfill(json({ ...RECORD, reviews: desk.investigated ? [desk.review] : [], requests: [request] }))
    }
    if (path.endsWith('/api/operator/reviews')) {
      const reviews = desk.investigated ? [desk.review] : []
      return route.fulfill(json({
        reviews, requests: [request], total: reviews.length,
        pendingCount: reviews.filter(review => review.humanState === 'confirmation_required').length,
        openRequestCount: desk.investigated ? 0 : 1,
      }))
    }
    if (path.endsWith('/api/operator/reviews/41/confirm')) {
      desk.review = APPROVED_REVIEW
      return route.fulfill(json({ reviewId: 41, status: 'approved', humanState: 'confirmed', decidedBy: 'sub-nadia', decidedByName: 'nadia', decidedAt: '2026-10-04T15:02:00Z', assurance: APPROVED_REVIEW.assurance }))
    }
    if (path.endsWith('/api/operator/reviews/41/execute')) {
      desk.executions += 1
      const denied = desk.executions === 1
      desk.review = denied ? DENIED_REVIEW : EXECUTED_REVIEW
      desk.record = denied ? NOTHING_WRITTEN : RECORDED_ONCE
      return route.fulfill(json(executeResult(desk)))
    }
    if (path.endsWith('/api/operator/reviews/41')) return route.fulfill(json(detail(desk.review, desk.record)))
    if (path.includes('/api/persona/')) return route.fulfill(json({ persona: null }))
    return route.fulfill(json({}))
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('pellier-auth-session:staff', '1')
    localStorage.setItem('pellier-builder-view', 'on')
    localStorage.removeItem('pellier-theme')
  })
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} theme at ${width}px: investigation, approval, DENY, ALLOW, replay`, async ({ page }) => {
      test.setTimeout(120_000)
      const desk: Desk = { review: PENDING_REVIEW, record: null, investigated: false, executions: 0 }
      await stubDesk(page, desk)
      await page.emulateMedia({ colorScheme: theme })
      await page.setViewportSize({ width, height: width < 760 ? 844 : 900 })
      const shot = (name: string) => join(SHOTS, `${name}-${theme}-${width}.png`)

      await page.goto('/operator/clients/CUST-JESSICA')
      await page.getByTestId('operator-investigate').click()
      await expect(page.getByTestId('operator-proposed-credit')).toBeVisible()
      await expect(page.getByTestId('operator-credit-request')).toContainText('Investigated')
      await expect(page.getByTestId('operator-reviews-link-count')).toHaveText(/^1/)
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('1-record-after-investigation'), fullPage: true })

      await page.goto('/operator/reviews/41')
      await page.getByTestId('operator-review-confirm').click()
      await expect(page.getByText('Approved by Nadia')).toBeVisible()
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('2-review-approved'), fullPage: true })

      await expect(page.getByTestId('operator-review-execute')).toHaveText('Execute')
      await page.getByTestId('operator-review-execute').click()
      await expect(page.getByTestId('operator-credit-denied')).toBeVisible()
      await expect(page.getByTestId('operator-review-execute')).toHaveText('Execute again')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('3-execute-deny'), fullPage: true })

      await page.getByTestId('operator-review-execute').click()
      await expect(page.getByTestId('operator-credit-recorded')).toContainText('Credit #12 recorded')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('4-execute-again-allow'), fullPage: true })

      await expect(page.getByTestId('operator-review-retry')).toHaveText('Replay with the same key')
      await page.getByTestId('operator-review-retry').click()
      await expect(page.getByTestId('operator-credit-replayed')).toContainText('Replayed, no new row')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('5-replay'), fullPage: true })
    })
  }
}
