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
import { ANNA, ANNA_FINDING, ANNA_ME, ANNA_QUESTION, ANNA_TURN_EVENTS, sseBody } from './fixtures/anna-turn'
import { catalogPage, resultCards } from './fixtures/surfaces'

const SHOTS = process.env.ASK_PELLIER_SHOTS ?? 'test-results/ask-pellier'
const PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8+vTpfwAJIwOf0z0/4gAAAABJRU5ErkJggg==',
  'base64',
)

// The storefront's own product shape (`PellierProduct`), for the hero and
// grid: the same three catalog rows the turn names, with their own photos.
const PRODUCTS = [
  { id: 31, name: 'Stoneware Pour-Over Set', brand: 'Pellier', color: 'Ash gray', price: 58, category: 'Kitchen and table', imageUrl: '/products/theo-stoneware-pour-over-set.webp', rating: 4.9, reviewCount: 134, tags: ['ceramic', 'slow', 'home'] },
  { id: 36, name: 'Ceramic Tumblers', brand: 'Pellier', color: 'Speckled charcoal', price: 34, category: 'Kitchen and table', imageUrl: '/products/theo-ceramic-tumblers.webp', rating: 4.7, reviewCount: 245, tags: ['ceramic', 'slow', 'home'] },
  { id: 22, name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'White', price: 44, category: 'Kitchen and table', imageUrl: '/products/anna-linen-napkins.webp', rating: 4.7, reviewCount: 178, tags: ['linen', 'gift', 'home'] },
]

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
    // Anna was signed in by the shopper chooser: the server reports her session.
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
    if (path.endsWith('/api/products')) return route.fulfill(json(PRODUCTS))
    if (path.endsWith('/api/scenarios')) {
      return route.fulfill(json({
        scenarios: [
          { id: 1, ordinal: 1, prompt: ANNA_QUESTION, journeyRole: 'required' },
          { id: 2, ordinal: 2, prompt: 'Which of those would you pick for a small kitchen?', journeyRole: 'required' },
          { id: 3, ordinal: 3, prompt: 'Which of these would you gift-wrap?', journeyRole: 'required' },
        ],
      }))
    }
    if (path.includes('/api/agent/session/')) return route.fulfill(json({ turns: [] }))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
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
    localStorage.setItem('pellier-auth-session:shopper', '1')
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
    await expect(drawer.getByText(ANNA_FINDING)).toBeVisible()
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-writing.png`) })

    // After the reveal: the steps fold, the cards sit after the prose.
    await expect(drawer.getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
    await expect(drawer.getByText('Stoneware Pour-Over Set').first()).toBeVisible()
    // No sold-out or over-budget card on Anna's turn.
    await expect(drawer.getByText('Sold out')).toHaveCount(0)
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-answered.png`) })

    // Builder view on, from the header: layer tags and the evidence line in
    // the dock, How it ranked once, on the page above the results.
    await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
    await drawer.getByTestId('turn-fold').click()
    await expect(drawer.getByTestId('ranking-summary')).toContainText('Kept 64 of 100')
    await expect(drawer.getByTestId('ranking-panel')).toHaveCount(0)
    const panel = page.getByTestId('results-view').getByTestId('ranking-panel')
    await expect(panel).toBeVisible()
    for (const chip of ['Kept 64 of 100', '31 over budget', '1 sold out', '4 candles', 'Full text 20', 'Vector 20']) {
      await expect(panel.getByText(chip, { exact: true })).toBeVisible()
    }
    // The verified principal for the turn, from the server, not the chooser.
    await expect(drawer.getByTestId('turn-principal')).toHaveText('IdentityWorkshop sign-in, CUST-ANNA')
    await page.addStyleTag({ content: '.cd-latest { visibility: hidden !important; }' })
    await page.waitForTimeout(400)
    await drawer.screenshot({ path: join(SHOTS, `anna-${width}-builder.png`) })
    await expect(page.evaluate(() => localStorage.getItem('pellier-builder-view'))).resolves.toBe('on')
  })
}
