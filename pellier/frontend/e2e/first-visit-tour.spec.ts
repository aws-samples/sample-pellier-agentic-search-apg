/**
 * The tour in a real browser, against the recorded fixtures
 * (`fixtures/surfaces.ts`, `fixtures/jessica-case.ts`). No backend or model
 * runs.
 *
 * It checks what jsdom cannot: the card takes focus as a chapter opens (a
 * browser will not focus a hidden element), each stop rings a control that is
 * laid out and on screen, a stop further down the page is brought into view,
 * and the card stays inside the viewport at a laptop and a phone width. It
 * also checks that the tour never presses Investigate or Approve.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/first-visit-tour.spec.ts
 */
import { expect, test, type Locator, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { ANNA_QUESTION } from './fixtures/anna-turn'
import {
  ANSWERED_REQUEST, BOOK, INVESTIGATION_EVENTS, INVESTIGATION_TAIL, NADIA_ME, OPEN_REQUEST, PENDING_REVIEW,
  RECORD, detail, sse,
} from './fixtures/jessica-case'
import { stubStorefront, visit } from './fixtures/surfaces'
import { liveDelayMs, relayFrames } from './fixtures/terminal-relay'

const STOPS = ['Ask Pellier', 'Builder view', 'The Operator', 'Choose a shopper']
const LAPTOPS = [{ width: 1440, height: 900 }, { width: 1280, height: 720 }]
const RING_PAD = 6

const card = (page: Page, title: string) => page.getByRole('dialog', { name: `Pellier tour: ${title}` })

/** The card has focus and sits wholly inside the viewport, a gutter in from each side. */
async function expectCardOnScreen(page: Page, title: string, timeout = 5_000) {
  const dialog = card(page, title)
  await expect(dialog).toBeVisible({ timeout })
  await expect(dialog).toBeFocused()
  const viewport = page.viewportSize()!
  const box = (await dialog.boundingBox())!
  expect(box.x).toBeGreaterThanOrEqual(16)
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 16)
  expect(box.y).toBeGreaterThanOrEqual(0)
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height)
  return dialog
}

/** The ring hugs the control, and the control is on screen: not scrolled away, not clipped by its column. */
async function expectRingOn(page: Page, target: Locator) {
  await expect(page.getByTestId('spotlight-tour')).toHaveAttribute('data-target', 'ring')
  await expect(target).toBeInViewport({ ratio: 0.5 })
  await expect.poll(async () => {
    const [ring, control] = await Promise.all([page.getByTestId('spotlight-tour-ring').boundingBox(), target.boundingBox()])
    if (!ring || !control) return 'not laid out'
    const gap = Math.max(
      Math.abs(ring.x - (control.x - RING_PAD)),
      Math.abs(ring.y - (control.y - RING_PAD)),
      Math.abs(ring.width - (control.width + RING_PAD * 2)),
      Math.abs(ring.height - (control.height + RING_PAD * 2)),
    )
    return gap <= 1 ? 'on the control' : `off the control by ${Math.round(gap)}px`
  }).toBe('on the control')
}

async function nextStop(page: Page, title: string, last = false) {
  await card(page, title).getByRole('button', { name: last ? 'Done' : 'Next' }).click()
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`the Storefront chapter on a first visit at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await visit(page, { signedIn: false, overlay: true })
    await stubStorefront(page, { signedIn: false })
    await page.goto('/')

    const overlay = page.getByTestId('spotlight-tour')
    for (const [index, title] of STOPS.entries()) {
      const dialog = await expectCardOnScreen(page, title)
      await expect(dialog.getByRole('button', { name: 'Skip' })).toBeVisible()
      // On a phone only Ask Pellier stays in the bar: the switches fold into the menu and the dock is closed.
      const ringed = viewport.width > 560 || index === 0
      await expect(overlay).toHaveAttribute('data-target', ringed ? 'ring' : 'none')
      await nextStop(page, title, index === STOPS.length - 1)
    }
    await expect(overlay).toHaveCount(0)

    await page.reload()
    await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
    await page.waitForTimeout(1000)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}

test('the last Storefront stop rings the shoppers in the dock', async ({ page }) => {
  await page.setViewportSize(LAPTOPS[0])
  await visit(page, { signedIn: false, overlay: true })
  await stubStorefront(page, { signedIn: false })
  await page.goto('/')
  for (const title of STOPS.slice(0, 3)) {
    await expectCardOnScreen(page, title)
    await nextStop(page, title)
  }
  await expectCardOnScreen(page, 'Choose a shopper')
  await expectRingOn(page, page.getByTestId('chat-drawer').getByTestId('ask-shoppers'))
})

test('?tour=off keeps every chapter closed', async ({ page }) => {
  await page.setViewportSize(LAPTOPS[0])
  await visit(page, { overlay: true })
  await stubStorefront(page)
  await page.goto('/?tour=off')
  const ask = page.getByTestId('pellier-hero-search')
  await expect(ask).toBeVisible()
  await page.waitForTimeout(1000)
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // An answer settles in the same tab: the answer chapter stays closed too.
  await ask.fill(ANNA_QUESTION)
  await ask.press('Enter')
  await expect(page.getByTestId('chat-drawer').getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(1000)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

for (const viewport of LAPTOPS) {
  test(`the answer chapter opens when the first answer settles, at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await visit(page, { overlay: true })
    // This browser has seen the Storefront chapter; the answer chapter is new to it.
    await page.addInitScript(() => localStorage.setItem('pellier-storefront-spotlight-seen', 'true'))
    await stubStorefront(page)
    await page.goto('/')
    await page.waitForTimeout(1000)
    await expect(page.getByRole('dialog')).toHaveCount(0)

    const ask = page.getByTestId('pellier-hero-search')
    await ask.fill(ANNA_QUESTION)
    await ask.press('Enter')
    const dock = page.getByTestId('chat-drawer')

    await expectCardOnScreen(page, 'Who asked', 30_000)
    await expectRingOn(page, dock.getByTestId('turn-principal').last())
    await nextStop(page, 'Who asked')

    await expectCardOnScreen(page, 'How Pellier answered')
    await expectRingOn(page, dock.getByTestId('turn-fold').last())
    await nextStop(page, 'How Pellier answered')

    await expectCardOnScreen(page, 'How it ranked')
    await expectRingOn(page, page.locator('.results-ranking'))
    await nextStop(page, 'How it ranked', true)
    await expect(page.getByTestId('spotlight-tour')).toHaveCount(0)

    // Seen once: a second answer in the same browser opens nothing.
    await ask.fill(ANNA_QUESTION)
    await ask.press('Enter')
    await expect(dock.getByTestId('turn-fold')).toHaveCount(2, { timeout: 20_000 })
    await page.waitForTimeout(1000)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}

/**
 * `/api/chat/watch` as the backend serves it: one turn sent from the terminal.
 * A replay arrives whole, as it does for a shopper chosen after the request
 * finished; a live one arrives frame by frame.
 */
async function relayServer(replay: boolean): Promise<{ server: Server; url: string }> {
  const server = createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' })
    res.write(': keep-alive\n\n')
    const frames = relayFrames(replay)
    let index = 0
    let timer: NodeJS.Timeout
    const next = () => {
      if (index >= frames.length) return
      res.write(`data: ${JSON.stringify(frames[index++])}\n\n`)
      timer = setTimeout(next, replay ? 5 : liveDelayMs(frames[index] ?? {}))
    }
    timer = setTimeout(next, 500)
    req.on('close', () => clearTimeout(timer))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  return { server, url: `http://127.0.0.1:${(server.address() as AddressInfo).port}/watch` }
}

for (const replay of [true, false]) {
  const how = replay ? 'opened after it finished' : 'watched as it streams'
  test(`the answer chapter opens for a request sent from the terminal, ${how}`, async ({ page }) => {
    test.setTimeout(120_000)
    const relay = await relayServer(replay)
    try {
      await page.setViewportSize(LAPTOPS[0])
      await visit(page, { overlay: true })
      await page.addInitScript(() => localStorage.setItem('pellier-storefront-spotlight-seen', 'true'))
      await stubStorefront(page)
      // Registered last, so it answers first: the relay streams from the server above.
      await page.route('**/api/chat/watch', route => route.continue({ url: relay.url }))
      await page.goto('/')

      // The labs' path: nobody types in the app. Anna is the shopper, and her request arrives from the terminal.
      const dock = page.getByTestId('chat-drawer')
      await expect(dock.getByText('Sent from the terminal', { exact: false })).toBeVisible({ timeout: 20_000 })

      await expectCardOnScreen(page, 'Who asked', 60_000)
      await expect(card(page, 'Who asked')).toContainText('1 of 3')
      await expectRingOn(page, dock.getByTestId('turn-principal').last())
      await nextStop(page, 'Who asked')
      await expectCardOnScreen(page, 'How Pellier answered')
      await expectRingOn(page, dock.getByTestId('turn-fold').last())
      await nextStop(page, 'How Pellier answered')
      await expectCardOnScreen(page, 'How it ranked')
      await expectRingOn(page, page.locator('.results-ranking'))
      await nextStop(page, 'How it ranked', true)
      await expect(page.getByTestId('spotlight-tour')).toHaveCount(0)
    } finally {
      // The page still holds the watch stream open, and close() waits for it.
      relay.server.closeAllConnections()
      await new Promise<void>(resolve => relay.server.close(() => resolve()))
    }
  })
}

interface Desk { investigated: boolean; decisions: number }

/** The Operator API: Nadia signed in, Jessica's open request, and a review that waits for her. */
async function stubDesk(page: Page, desk: Desk) {
  const json = (body: unknown) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/ports\/\d+/, '')
    const reviews = desk.investigated ? [PENDING_REVIEW] : []
    const request = desk.investigated ? ANSWERED_REQUEST : OPEN_REQUEST
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(NADIA_ME))
    if (path.endsWith('/api/operator/clients')) return route.fulfill(json(BOOK))
    if (path.endsWith('/api/operator/clients/CUST-JESSICA/investigate')) {
      desk.investigated = true
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([...INVESTIGATION_EVENTS, ...INVESTIGATION_TAIL]) })
    }
    if (path.endsWith('/api/operator/clients/CUST-JESSICA')) return route.fulfill(json({ ...RECORD, reviews, requests: [request] }))
    if (path.endsWith('/api/operator/reviews')) {
      return route.fulfill(json({
        reviews, requests: [request], total: reviews.length, pendingCount: reviews.length,
        openRequestCount: desk.investigated ? 0 : 1,
      }))
    }
    if (/\/api\/operator\/reviews\/41\/(confirm|decline|execute)$/.test(path)) {
      desk.decisions += 1
      return route.fulfill(json({}))
    }
    if (path.endsWith('/api/operator/reviews/41')) return route.fulfill(json(detail(PENDING_REVIEW)))
    if (path.includes('/api/persona/')) return route.fulfill(json({ persona: null }))
    return route.fulfill(json({}))
  })
}

for (const viewport of [...LAPTOPS, { width: 390, height: 844 }]) {
  test(`the Operator chapters ring the desk, then the proposal, at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.addInitScript(() => {
      localStorage.setItem('pellier-auth-session:staff', '1')
      localStorage.setItem('pellier-builder-view', 'on')
      localStorage.removeItem('pellier-theme')
    })
    const desk: Desk = { investigated: false, decisions: 0 }
    await stubDesk(page, desk)
    await page.goto('/operator/clients/CUST-JESSICA')

    // The desk chapter opens once Jessica's record has loaded.
    await expectCardOnScreen(page, 'Clients and Reviews')
    await expectRingOn(page, page.locator('.op-bar-sections'))
    await nextStop(page, 'Clients and Reviews')
    await expectCardOnScreen(page, 'Asked in chat')
    await expectRingOn(page, page.getByTestId('operator-credit-request'))
    await nextStop(page, 'Asked in chat')
    await expectCardOnScreen(page, 'Investigate')
    await expectRingOn(page, page.getByTestId('operator-investigate'))
    await nextStop(page, 'Investigate', true)
    await expect(page.getByTestId('spotlight-tour')).toHaveCount(0)
    // The tour rang Investigate; it did not press it.
    expect(desk.investigated).toBe(false)

    // The proposal chapter opens once the investigation ends with a credit waiting.
    await page.getByTestId('operator-investigate').click()
    await expectCardOnScreen(page, 'What the records show', 20_000)
    await expectRingOn(page, page.getByTestId('operator-brief'))
    await nextStop(page, 'What the records show')
    await expectCardOnScreen(page, 'Three checks')
    await expectRingOn(page, page.getByTestId('operator-credit-checks'))
    await nextStop(page, 'Three checks')
    await expectCardOnScreen(page, 'Your decision')
    await expectRingOn(page, page.locator('[data-tour="credit-decision"]'))
    await nextStop(page, 'Your decision', true)
    await expect(page.getByTestId('spotlight-tour')).toHaveCount(0)

    // Nothing was decided for the visitor: the credit still waits, and Approve is theirs to press.
    expect(desk.decisions).toBe(0)
    await expect(page.getByTestId('operator-review-confirm')).toBeEnabled()

    // Seen once: the same record opens neither chapter again.
    await page.reload()
    await expect(page.getByTestId('operator-record')).toBeVisible()
    await page.waitForTimeout(1000)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}

test('the replay button on the Operator plays the chapters on the page', async ({ page }) => {
  await page.setViewportSize(LAPTOPS[0])
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.setItem('pellier-auth-session:staff', '1')
  })
  await stubDesk(page, { investigated: false, decisions: 0 })
  await page.goto('/operator/clients/CUST-JESSICA')
  await expect(page.getByTestId('operator-record')).toBeVisible()
  await page.waitForTimeout(1000)
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await page.getByRole('button', { name: 'Show the tour' }).click()
  const dialog = await expectCardOnScreen(page, 'Clients and Reviews')
  await expect(dialog).toContainText('1 of 3')
  await dialog.getByRole('button', { name: 'Skip' }).click()
  await expect(page.getByRole('button', { name: 'Show the tour' })).toBeFocused()
})
