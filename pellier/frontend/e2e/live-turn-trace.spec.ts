/**
 * A turn sent from the terminal appears in Ask Pellier, labelled, with its
 * Builder view trace, streaming as the relay delivers it.
 *
 * Every `/api` call is answered from fixtures; `/api/chat/watch` is served by a
 * small streaming server in this process, so frames arrive over time as they
 * would from the backend. Run against the Vite dev server:
 *
 *   npx vite --port 5174 &
 *   E2E_BASE_URL=http://localhost:5174 npx playwright test e2e/live-turn-trace.spec.ts
 *
 * Set LIVE_TRACE_SHOTS=<dir> to also save stills and a video of the stream.
 */
import { expect, test, type Page } from '@playwright/test'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ANNA, ANNA_FINDING, ANNA_ME } from './fixtures/anna-turn'
import { catalogPage, resultCards } from './fixtures/surfaces'
import { liveDelayMs, relayFrames } from './fixtures/terminal-relay'

const SHOTS = process.env.LIVE_TRACE_SHOTS
const PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8+vTpfwAJIwOf0z0/4gAAAABJRU5ErkJggg==',
  'base64',
)

// With stills requested, record the stream too: the video is the prototype's main view.
test.use({ video: SHOTS ? { mode: 'on', size: { width: 1440, height: 900 } } : 'off' })

let server: Server
let watchUrl = ''

test.beforeAll(async () => {
  // One relayed turn per connection, after a short pause, frame by frame.
  server = createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' })
    res.write(': keep-alive\n\n')
    const frames = relayFrames(false)
    let index = 0
    let timer: NodeJS.Timeout
    const next = () => {
      if (index >= frames.length) return
      const frame = frames[index++] as { type?: string; event?: { type?: string; status?: string } }
      res.write(`data: ${JSON.stringify(frame)}\n\n`)
      timer = setTimeout(next, liveDelayMs(frames[index] ?? {}))
    }
    timer = setTimeout(next, 1500)
    req.on('close', () => clearTimeout(timer))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  watchUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}/watch`
})

test.afterAll(async () => {
  await new Promise<void>(resolve => server.close(() => resolve()))
})

async function stubApi(page: Page) {
  const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/assets/personas/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1x1 }))
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/ports\/\d+/, '')
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(ANNA_ME))
    if (path.includes('/api/auth/')) return route.fulfill(json({ detail: 'not signed in' }, 401))
    if (path.endsWith('/api/personas')) return route.fulfill(json([ANNA]))
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: ANNA }))
    if (path.endsWith('/api/persona/switch')) return route.fulfill(json({ session_id: 'session-shots', persona: ANNA }))
    if (path.endsWith('/api/products') && url.searchParams.has('ids')) {
      return route.fulfill(json(resultCards(url.searchParams.get('ids') ?? '')))
    }
    if (path.endsWith('/api/products') && url.searchParams.has('page')) {
      const { status, body } = catalogPage(Number(url.searchParams.get('page')), Number(url.searchParams.get('page_size') ?? 12))
      return route.fulfill(json(body, status))
    }
    if (path.includes('/api/agent/session/')) return route.fulfill(json({ turns: [] }))
    return route.fulfill(json({}))
  })
  // Registered last, so it answers first: the relay streams from the server above.
  await page.route('**/api/chat/watch', route => route.continue({ url: watchUrl }))
}

for (const theme of ['light', 'dark'] as const) {
  test(`a terminal turn streams into Ask Pellier with its trace (${theme})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.addInitScript(({ persona, theme }) => {
      sessionStorage.setItem('pellier-persona', JSON.stringify(persona))
      localStorage.setItem('pellier-session-id', 'session-shots')
      localStorage.setItem('pellier-auth-session:shopper', '1')
      localStorage.removeItem('pellier-drawer-storefront')
      localStorage.setItem('pellier-builder-view', 'on')
      localStorage.setItem('pellier-theme', theme)
    }, { persona: ANNA, theme })
    await stubApi(page)
    if (SHOTS) mkdirSync(SHOTS, { recursive: true })

    await page.goto('/')
    const drawer = page.getByTestId('chat-drawer')
    if (!(await drawer.isVisible())) await page.getByRole('button', { name: 'Ask Pellier' }).first().click()
    await expect(drawer).toBeVisible()

    // The turn arrives from the terminal, labelled, and its trace streams in.
    await expect(drawer.getByText('Sent from the terminal', { exact: false })).toBeVisible({ timeout: 15_000 })
    await expect(drawer.getByText('Searching the catalog in Aurora').first()).toBeVisible({ timeout: 15_000 })
    if (SHOTS) await drawer.screenshot({ path: join(SHOTS, `terminal-turn-${theme}-1-searching.png`) })
    await expect(drawer.getByText(ANNA_FINDING)).toBeVisible({ timeout: 15_000 })
    if (SHOTS) await page.screenshot({ path: join(SHOTS, `terminal-turn-${theme}-2-found.png`) })

    // Answered: the cards, and How it ranked on the page beside the dock.
    await expect(drawer.getByText('Stoneware Pour-Over Set').first()).toBeVisible({ timeout: 30_000 })
    await expect(drawer.getByTestId('turn-fold')).toBeVisible({ timeout: 30_000 })
    const panel = page.getByTestId('results-view').getByTestId('ranking-panel')
    await expect(panel).toBeVisible({ timeout: 15_000 })
    await expect(panel.getByText('Kept 64 of 100', { exact: true })).toBeVisible()
    // The verified principal for the turn, as the relay delivered it.
    await drawer.getByTestId('turn-fold').click()
    await expect(drawer.getByTestId('turn-principal')).toHaveText('IdentityWorkshop sign-in, CUST-ANNA')
    if (SHOTS) {
      await page.waitForTimeout(500)
      await page.screenshot({ path: join(SHOTS, `terminal-turn-${theme}-3-answered.png`) })
      await drawer.screenshot({ path: join(SHOTS, `terminal-turn-${theme}-4-panel.png`) })
    }
  })
}
