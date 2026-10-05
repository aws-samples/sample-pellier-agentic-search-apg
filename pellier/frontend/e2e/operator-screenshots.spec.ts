/**
 * The Operator desk in both themes, against the real app with recorded
 * fixtures: the clients, Jessica's record, the investigation streaming, the
 * review record and the executed credit, at 1440px and 390px.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 OPERATOR_SHOTS=/path/to/dir \
 *     npx playwright test e2e/operator-screenshots.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import {
  ANSWERED_REQUEST, APPROVED_REVIEW, BOOK, EXECUTED_REVIEW, EXECUTE_RESULT, INVESTIGATION_EVENTS,
  INVESTIGATION_TAIL, NADIA_ME, OPEN_REQUEST, PENDING_REVIEW, RECORD, RECORDED_ONCE, detail, sse,
} from './fixtures/jessica-case'

const SHOTS = process.env.OPERATOR_SHOTS ?? 'test-results/operator'

/** The desk's state machine, advanced by the decisions the page makes. */
interface Desk {
  review: Record<string, unknown>
  record: Record<string, unknown> | null
  investigated: boolean
}

async function stubDesk(page: Page, desk: Desk, options: { streamDelayMs?: number } = {}) {
  const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/ports\/\d+/, '')
    const method = route.request().method()
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(NADIA_ME))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.endsWith('/api/operator/clients')) return route.fulfill(json(BOOK))
    if (path.endsWith('/api/operator/clients/CUST-JESSICA/investigate') && method === 'POST') {
      desk.investigated = true
      // The planner's step and the answer land after a pause, so a capture can
      // catch the Investigator's reads with the Planner still running.
      if (options.streamDelayMs) {
        const head = sse(INVESTIGATION_EVENTS)
        const tail = sse(INVESTIGATION_TAIL)
        await route.fulfill({
          status: 200, contentType: 'text/event-stream',
          body: head + tail,
        })
        return
      }
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([...INVESTIGATION_EVENTS, ...INVESTIGATION_TAIL]) })
    }
    // Jessica asked in chat for a store credit: one open request with no
    // amount, answered by the investigation.
    const request = desk.investigated ? ANSWERED_REQUEST : OPEN_REQUEST
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
      desk.review = EXECUTED_REVIEW
      desk.record = RECORDED_ONCE
      return route.fulfill(json(EXECUTE_RESULT))
    }
    if (path.endsWith('/api/operator/reviews/41')) return route.fulfill(json(detail(desk.review, desk.record)))
    if (path.includes('/api/persona/')) return route.fulfill(json({ persona: null }))
    return route.fulfill(json({}))
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.setItem('pellier-auth-session:staff', '1')
    localStorage.setItem('pellier-builder-view', 'on')
    localStorage.removeItem('pellier-theme')
  })
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} theme at ${width}px: clients, record, investigation, review, executed credit`, async ({ page }) => {
      test.setTimeout(120_000)
      const desk: Desk = { review: PENDING_REVIEW, record: null, investigated: false }
      await stubDesk(page, desk)
      await page.emulateMedia({ colorScheme: theme })
      await page.setViewportSize({ width, height: 960 })
      const shot = (name: string) => join(SHOTS, `${name}-${theme}-${width}.png`)

      // Clients: open requests and the last order, no tiers.
      await page.goto('/operator')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await expect(page.getByTestId('operator-book')).toBeVisible()
      await expect(page.getByTestId('operator-client-jessica')).toContainText('1 open request')
      await expect(page.getByTestId('operator-staff')).toContainText('Nadia')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('clients'), fullPage: width < 760 })

      // Jessica's record: the ticket, the two Returned orders, no credit.
      await page.getByTestId('operator-client-jessica').click()
      await expect(page.getByTestId('operator-record')).toBeVisible()
      await expect(page.getByTestId('operator-order-301')).toContainText('Returned')
      await expect(page.getByTestId('operator-credits-none')).toBeVisible()
      await expect(page.getByTestId('operator-credit-request')).toContainText('Open request')
      await expect(page.getByTestId('operator-credit-request')).toContainText('no amount')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('record'), fullPage: true })

      // The investigation streaming: the reads done, the Planner running.
      await page.getByTestId('operator-investigate').click()
      await expect(page.getByTestId('turn-status')).toBeVisible()
      await expect(page.getByTestId('operator-brief')).toBeVisible()
      await expect(page.getByTestId('operator-proposed-credit')).toBeVisible()
      await expect(page.getByTestId('operator-proposed-credit')).toContainText('Waiting for Nadia')
      await expect(page.getByTestId('operator-credit-request')).toContainText('Investigated')
      if (width < 760) await page.getByTestId('operator-investigation').scrollIntoViewIfNeeded()
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('investigation'), fullPage: true })

      // The review record, then Approve.
      await page.goto('/operator/reviews/41')
      await expect(page.getByTestId('operator-review-record')).toBeVisible()
      await expect(page.getByTestId('operator-credit-amount')).toHaveText('$100.00')
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('review'), fullPage: true })
      await page.getByTestId('operator-review-confirm').click()
      await expect(page.getByText('Approved by Nadia')).toBeVisible()

      // Execute: one credit, one audit row.
      await page.getByTestId('operator-review-execute').click()
      await expect(page.getByTestId('operator-credit-recorded')).toContainText('Credit #12 recorded')
      await expect(page.getByTestId('operator-credit-checks')).toContainText('ALLOW')
      await expect(page.getByTestId('operator-credit-checks')).toContainText('Recorded once')
      await expect(page.getByTestId('operator-review-retry')).toBeVisible()
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('executed'), fullPage: true })
    })
  }
}
