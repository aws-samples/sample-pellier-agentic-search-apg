/**
 * Both themes on the direction A surfaces, against the real app with
 * recorded fixtures: Home, the collection, a product page and an Anna turn
 * with the Builder view on, at 1440px and 390px, plus the first-visit
 * overlay. The theme comes from the system preference with no stored
 * choice, which also proves the default.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 THEME_SHOTS=/path/to/dir \
 *     npx playwright test e2e/theme-screenshots.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ANNA, ANNA_ME, ANNA_QUESTION, ANNA_TURN_EVENTS, sseBody } from './fixtures/anna-turn'

const SHOTS = process.env.THEME_SHOTS ?? 'test-results/theme'
const PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8+vTpfwAJIwOf0z0/4gAAAABJRU5ErkJggg==',
  'base64',
)

const WAREHOUSES = [
  { warehouseId: 'BK-01', name: 'Brooklyn', city: 'Brooklyn, NY', quantity: 12, shipWindowMin: 1, shipWindowMax: 2 },
  { warehouseId: 'ATX-02', name: 'Austin', city: 'Austin, TX', quantity: 6, shipWindowMin: 2, shipWindowMax: 4 },
  { warehouseId: 'PDX-03', name: 'Portland', city: 'Portland, OR', quantity: 14, shipWindowMin: 3, shipWindowMax: 5 },
]

// The storefront's own product shape (`PellierProduct`), with the stock the
// listing now carries: all in stock, Austin and Portland only, sold out.
const PRODUCTS = [
  { id: 31, name: 'Stoneware Pour-Over Set', brand: 'Pellier', color: 'Ash gray', price: 58, category: 'Kitchen and table', imageUrl: '/products/theo-stoneware-pour-over-set.webp', rating: 4.9, reviewCount: 134, tags: ['ceramic', 'slow', 'home'], quantity: 32, warehouses: WAREHOUSES },
  { id: 36, name: 'Ceramic Tumblers', brand: 'Pellier', color: 'Speckled charcoal', price: 34, category: 'Kitchen and table', imageUrl: '/products/theo-ceramic-tumblers.webp', rating: 4.7, reviewCount: 245, tags: ['ceramic', 'slow', 'home'], quantity: 20, warehouses: [{ ...WAREHOUSES[0], quantity: 0 }, WAREHOUSES[1], WAREHOUSES[2]] },
  { id: 22, name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'White', price: 44, category: 'Kitchen and table', imageUrl: '/products/anna-linen-napkins.webp', rating: 4.7, reviewCount: 178, tags: ['linen', 'gift', 'home'], quantity: 24, warehouses: WAREHOUSES },
  { id: 12, name: 'Hadley Linen Shirt', brand: 'Hadley', color: 'Natural', price: 78, category: 'Clothing', imageUrl: '/products/fresh-hadley-linen-shirt.webp', rating: 4.8, reviewCount: 91, tags: ['linen', 'travel'], quantity: 0, warehouses: WAREHOUSES.map((w) => ({ ...w, quantity: 0 })) },
]
const DETAIL = {
  ...PRODUCTS[0],
  description: 'A stoneware dripper and carafe in ash gray that brews two cups by hand.',
  availability: { onHand: 32, warehouses: WAREHOUSES },
}
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
    // Anna was signed in by the shopper chooser: the server reports her session.
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(ANNA_ME))
    if (path.includes('/api/auth/')) return route.fulfill(json({ detail: 'not signed in' }, 401))
    if (path.endsWith('/api/personas')) return route.fulfill(json([ANNA]))
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: ANNA }))
    if (path.endsWith('/api/persona/switch')) return route.fulfill(json({ session_id: 'session-shots', persona: ANNA }))
    if (/\/api\/products\/\d+$/.test(path)) return route.fulfill(json(DETAIL))
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
    if (path.endsWith('/api/storefront/catalog-stats')) return route.fulfill(json(CATALOG_STATS))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    return route.fulfill(json({}))
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript((persona) => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    sessionStorage.setItem('pellier-persona', JSON.stringify(persona))
    localStorage.setItem('pellier-session-id', 'session-shots')
    localStorage.setItem('pellier-auth-session', '1')
    localStorage.removeItem('pellier-drawer-storefront')
    localStorage.removeItem('pellier-builder-view')
    localStorage.removeItem('pellier-theme')
  }, ANNA)
  await stubApi(page)
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} theme at ${width}px: home, collection, product, Anna's turn`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme })
      await page.setViewportSize({ width, height: 960 })
      const shot = (name: string) => join(SHOTS, `${name}-${theme}-${width}.png`)

      // Home: the system preference is the default and lands before paint.
      await page.goto('/')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await expect(page.getByRole('button', { name: 'System theme' })).toHaveAttribute('aria-pressed', 'true')
      await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
      await expect(page.getByTestId('product-card-36')).toContainText('In stock in Austin and Portland')
      await expect(page.getByTestId('product-card-12')).toContainText('Sold out')
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('home') })

      // The collection: the cards with their one stock line.
      await page.getByTestId('product-card-12').getByTestId('status-tag').scrollIntoViewIfNeeded()
      await page.waitForTimeout(600)
      await page.screenshot({ path: shot('collection') })

      // A product page.
      await page.goto('/product/31')
      await expect(page.getByTestId('product-detail-name')).toHaveText('Stoneware Pour-Over Set')
      await expect(page.getByTestId('product-availability')).toHaveAttribute('data-state', 'read')
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('product') })

      // Anna's turn in the docked panel, with the Builder view on.
      await page.goto('/')
      const ask = page.getByTestId('pellier-hero-search')
      await ask.fill(ANNA_QUESTION)
      await ask.press('Enter')
      const drawer = page.getByTestId('chat-drawer')
      await expect(drawer).toBeVisible()
      await expect(drawer.getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
      await drawer.getByRole('switch', { name: 'Builder view' }).click()
      await drawer.getByTestId('turn-fold').click()
      await expect(drawer.getByTestId('ranking-panel')).toBeVisible()
      if (width < 1080) await drawer.scrollIntoViewIfNeeded()
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('ask-pellier-builder') })
      await drawer.screenshot({ path: shot('ask-pellier-panel') })
    })
  }

  test(`${theme} theme: the first-visit overlay`, async ({ page }) => {
    // A new session: the overlay has not been seen yet.
    await page.addInitScript(() => sessionStorage.removeItem('pellier-storefront-spotlight-seen'))
    await page.emulateMedia({ colorScheme: theme })
    await page.setViewportSize({ width: 1440, height: 960 })
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    const dialog = page.getByRole('dialog', { name: 'Begin with the edit.' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Continue' })).toBeVisible()
    await page.waitForTimeout(700)
    await page.screenshot({ path: join(SHOTS, `spotlight-${theme}-1440.png`) })
  })
}
