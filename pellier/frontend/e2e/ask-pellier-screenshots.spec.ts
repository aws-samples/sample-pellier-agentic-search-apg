/**
 * Ask Pellier screenshots against the real app with a recorded turn.
 *
 * Every `/api` call is answered from fixtures, including the chat stream,
 * so the storefront renders one Anna turn without a backend or a model. Run
 * against the Vite dev server:
 *
 *   npx vite --port 5173 &
 *   E2E_BASE_URL=http://localhost:5173 ASK_PELLIER_SHOTS=/tmp/shots \
 *     npx playwright test e2e/ask-pellier-screenshots.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ANNA, ANNA_QUESTION, ANNA_TURN_EVENTS, sseBody } from './fixtures/anna-turn'

const SHOTS = process.env.ASK_PELLIER_SHOTS ?? 'test-results/ask-pellier'
const PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8+vTpfwAJIwOf0z0/4gAAAABJRU5ErkJggg==',
  'base64',
)

// The storefront's own product shape (`PellierProduct`), for the hero and grid.
const PRODUCTS = [
  { id: 65, name: 'Stoneware Mugs, Set of 2', brand: 'Pellier', color: 'Oat', price: 38, category: 'Kitchen and table', imageUrl: '/products/anna-ceramic-bud-vase-480.webp', rating: 4.7, reviewCount: 212, tags: ['ceramic', 'home'] },
  { id: 22, name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'Ivory', price: 44, category: 'Kitchen and table', imageUrl: '/products/anna-monogrammed-napkins-480.webp', rating: 4.8, reviewCount: 148, tags: ['linen', 'gift'] },
  { id: 27, name: 'Ceramic Bud Vase', brand: 'Pellier', color: 'Sand', price: 22, category: 'Home', imageUrl: '/products/anna-ceramic-bud-vase-480.webp', rating: 4.6, reviewCount: 96, tags: ['ceramic', 'home'] },
]
const CATALOG_STATS = {
  product_count: 100,
  category_count: 7,
  standout_name: 'Stoneware Pour-Over Set',
  standout_category: 'Kitchen and table',
  generated_at: '2026-10-04T00:00:00Z',
}

async function stubApi(page: Page) {
  const json = (body: unknown, status = 200) => ({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
  await page.route('**/assets/personas/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1x1 }))
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/ports\/\d+/, '')
    if (path.endsWith('/api/chat/stream')) {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sseBody(ANNA_TURN_EVENTS) })
    }
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.includes('/api/auth/')) return route.fulfill(json({ detail: 'not signed in' }, 401))
    if (path.endsWith('/api/personas')) return route.fulfill(json([ANNA]))
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: ANNA }))
    if (path.endsWith('/api/persona/switch')) return route.fulfill(json({ session_id: 'session-shots', persona: ANNA }))
    if (path.endsWith('/api/products')) return route.fulfill(json(PRODUCTS))
    if (path.endsWith('/api/scenarios')) {
      return route.fulfill(json({
        scenarios: [
          { id: 1, ordinal: 1, prompt: ANNA_QUESTION, journeyRole: 'required' },
          { id: 2, ordinal: 2, prompt: 'Help me pair the mugs with something else under $50.', journeyRole: 'required' },
          { id: 3, ordinal: 3, prompt: 'Which of these would you gift-wrap?', journeyRole: 'required' },
        ],
      }))
    }
    if (path.includes('/api/agent/session/')) return route.fulfill(json({ turns: [] }))
    if (path.endsWith('/api/storefront/catalog-stats')) return route.fulfill(json(CATALOG_STATS))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ detail: 'not signed in' }, 401))
    return route.fulfill(json({}))
  })
}

async function openDrawerAndAsk(page: Page) {
  await page.goto('/')
  // The hero's ask field opens the drawer with the question and sends it.
  const ask = page.getByTestId('pellier-hero-search')
  await ask.fill(ANNA_QUESTION)
  await ask.press('Enter')
  const drawer = page.getByTestId('chat-drawer')
  await expect(drawer).toBeVisible()
  return drawer
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript((persona) => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    sessionStorage.setItem('pellier-persona', JSON.stringify(persona))
    localStorage.setItem('pellier-session-id', 'session-shots')
    localStorage.removeItem('pellier-drawer-storefront')
    localStorage.removeItem('pellier-builder-view')
  }, ANNA)
  await stubApi(page)
  mkdirSync(SHOTS, { recursive: true })
})

for (const width of [1440, 390]) {
  test(`Anna's turn, Builder view off and on, at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    const drawer = await openDrawerAndAsk(page)

    // Mid-turn: the status line is writing and the steps carry their findings.
    await expect(drawer.getByTestId('turn-status')).toHaveText(/Writing your answer/)
    await expect(drawer.getByText('3 under $100 and in stock, candles left out')).toBeVisible()
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-writing.png`) })

    // After the reveal: the steps fold, the cards sit after the prose.
    await expect(drawer.getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
    await expect(drawer.getByText('Stoneware Mugs, Set of 2').first()).toBeVisible()
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-answered.png`) })

    // Builder view on: layer tags, the evidence line and how it ranked.
    await drawer.getByRole('switch', { name: 'Builder view' }).click()
    await drawer.getByTestId('turn-fold').click()
    await expect(drawer.getByTestId('ranking-panel')).toBeVisible()
    await expect(drawer.getByText('Kept 23 of 100')).toBeVisible()
    // Let the step rows finish rising before the capture.
    await page.waitForTimeout(400)
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-builder.png`) })
    await expect(page.evaluate(() => localStorage.getItem('pellier-builder-view'))).resolves.toBe('on')
  })
}
