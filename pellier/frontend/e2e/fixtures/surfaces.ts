/**
 * Every storefront and Operator surface, opened against recorded fixtures.
 *
 * `theme-surfaces.spec.ts` captures each one in both themes and runs the
 * dark contrast sweep on it; `theme-screenshots.spec.ts` shares the
 * storefront stubs. Each surface answers `/api` itself from the Anna turn
 * (`anna-turn.ts`) and Jessica's case (`jessica-case.ts`), so no backend or
 * model runs.
 */
import { expect, type Page } from '@playwright/test'
import { ANNA, ANNA_ME, ANNA_QUESTION, ANNA_TURN_EVENTS, sseBody } from './anna-turn'
import { ANNA_RESULT_CARDS } from './anna-cards'
import { HADLEY_RESULT_CARDS } from './two-searches-turn'
import { BOOK, NADIA_ME, OPEN_REQUEST, RECORD } from './jessica-case'

export const WAREHOUSES = [
  { warehouseId: 'BK-01', name: 'Brooklyn', city: 'Brooklyn, NY', quantity: 12, shipWindowMin: 1, shipWindowMax: 2 },
  { warehouseId: 'ATX-02', name: 'Austin', city: 'Austin, TX', quantity: 6, shipWindowMin: 2, shipWindowMax: 4 },
  { warehouseId: 'PDX-03', name: 'Portland', city: 'Portland, OR', quantity: 14, shipWindowMin: 3, shipWindowMax: 5 },
]

// The storefront's own product shape (`PellierProduct`), with the stock the
// listing now carries: all in stock, Austin and Portland only, sold out.
export const PRODUCTS = [
  { id: 31, name: 'Stoneware Pour-Over Set', brand: 'Pellier', color: 'Ash gray', price: 58, category: 'Kitchen and table', imageUrl: '/products/theo-stoneware-pour-over-set.webp', rating: 4.9, reviewCount: 134, tags: ['ceramic', 'slow', 'home'], quantity: 32, warehouses: WAREHOUSES },
  { id: 36, name: 'Ceramic Tumblers', brand: 'Pellier', color: 'Speckled charcoal', price: 34, category: 'Kitchen and table', imageUrl: '/products/theo-ceramic-tumblers.webp', rating: 4.7, reviewCount: 245, tags: ['ceramic', 'slow', 'home'], quantity: 20, warehouses: [{ ...WAREHOUSES[0], quantity: 0 }, WAREHOUSES[1], WAREHOUSES[2]] },
  { id: 22, name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'White', price: 44, category: 'Kitchen and table', imageUrl: '/products/anna-linen-napkins.webp', rating: 4.7, reviewCount: 178, tags: ['linen', 'gift', 'home'], quantity: 24, warehouses: WAREHOUSES },
  { id: 12, name: 'Hadley Linen Shirt', brand: 'Hadley', color: 'Natural', price: 78, category: 'Clothing', imageUrl: '/products/fresh-hadley-linen-shirt.webp', rating: 4.8, reviewCount: 91, tags: ['linen', 'travel'], quantity: 0, warehouses: WAREHOUSES.map((w) => ({ ...w, quantity: 0 })) },
]
/**
 * The home edit: twelve pieces, as every edit now holds, so the grid's rows
 * are full. The four above (one per stock line) lead; eight of Anna's
 * recorded result cards follow.
 */
export const HOME_EDIT = [
  ...PRODUCTS,
  ...ANNA_RESULT_CARDS.filter(card => !PRODUCTS.some(product => product.id === card.id)).slice(0, 8),
]
export const DETAIL = {
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
const SCENARIOS = {
  scenarios: [
    { id: 1, ordinal: 1, prompt: ANNA_QUESTION, journeyRole: 'required' },
    { id: 2, ordinal: 2, prompt: 'Which of those would you pick for a small kitchen?', journeyRole: 'required' },
    { id: 3, ordinal: 3, prompt: 'Which of these would you gift-wrap?', journeyRole: 'required' },
  ],
}

const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })

const RECORDED_CARDS = [...ANNA_RESULT_CARDS, ...HADLEY_RESULT_CARDS]

/** `GET /api/products?ids=`: the recorded cards for exactly those ids, in that order. */
export function resultCards(ids: string): unknown[] {
  return ids.split(',').filter(Boolean)
    .map(id => RECORDED_CARDS.find(card => String(card.id) === id))
    .filter(Boolean)
}

interface StorefrontStub {
  signedIn?: boolean
  /** The turn the chat stream replays; Anna's by default. */
  turn?: object[]
}

/** The storefront API: Anna signed in by the shopper chooser, or nobody. */
export async function stubStorefront(page: Page, { signedIn = true, turn = ANNA_TURN_EVENTS }: StorefrontStub = {}) {
  await page.route('**/api/**', (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/ports\/\d+/, '')
    if (path.endsWith('/api/chat/stream')) {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sseBody(turn) })
    }
    if (path.endsWith('/api/products') && url.searchParams.has('ids')) {
      return route.fulfill(json(resultCards(url.searchParams.get('ids') ?? '')))
    }
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.endsWith('/api/auth/me')) return route.fulfill(signedIn ? json(ANNA_ME) : json({ detail: 'not signed in' }, 401))
    if (path.includes('/api/auth/')) return route.fulfill(json({ detail: 'not signed in' }, 401))
    if (path.endsWith('/api/personas')) return route.fulfill(json([ANNA]))
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: signedIn ? ANNA : null }))
    if (path.endsWith('/api/persona/switch')) return route.fulfill(json({ session_id: 'session-shots', persona: ANNA }))
    if (/\/api\/products\/\d+$/.test(path)) return route.fulfill(json(DETAIL))
    if (path.endsWith('/api/products')) return route.fulfill(json(HOME_EDIT))
    if (path.endsWith('/api/scenarios')) return route.fulfill(json(SCENARIOS))
    if (path.includes('/api/agent/session/')) return route.fulfill(json({ turns: [] }))
    if (path.endsWith('/api/storefront/catalog-stats')) return route.fulfill(json(CATALOG_STATS))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    return route.fulfill(json({}))
  })
}

/** The Operator desk API: Nadia signed in, Jessica's open request. */
async function stubOperator(page: Page) {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/ports\/\d+/, '')
    if (path.endsWith('/api/auth/me')) return route.fulfill(json(NADIA_ME))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    if (path.endsWith('/api/health')) return route.fulfill(json({ status: 'ok' }))
    if (path.endsWith('/api/operator/clients')) return route.fulfill(json(BOOK))
    if (path.endsWith('/api/operator/clients/CUST-JESSICA')) return route.fulfill(json({ ...RECORD, reviews: [], requests: [OPEN_REQUEST] }))
    if (path.endsWith('/api/operator/reviews')) {
      return route.fulfill(json({ reviews: [], requests: [OPEN_REQUEST], total: 0, pendingCount: 0, openRequestCount: 1 }))
    }
    if (path.includes('/api/persona/')) return route.fulfill(json({ persona: null }))
    return route.fulfill(json({}))
  })
}

interface Visit {
  signedIn?: boolean
  overlay?: boolean
  cart?: boolean
}

/** The storage a visit starts with, set before the first script runs. */
export async function visit(page: Page, { signedIn = true, overlay = false, cart = false }: Visit = {}) {
  await page.addInitScript(({ persona, signedIn, overlay, cart }) => {
    if (!overlay) sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.removeItem('pellier-theme')
    localStorage.removeItem('pellier-drawer-storefront')
    localStorage.removeItem('pellier-builder-view')
    localStorage.setItem('pellier-session-id', 'session-shots')
    if (signedIn) {
      sessionStorage.setItem('pellier-persona', JSON.stringify(persona))
      localStorage.setItem('pellier-auth-session:shopper', '1')
    }
    if (cart) {
      localStorage.setItem('pellier-cart-session', 'session-shots')
      localStorage.setItem('pellier-cart', JSON.stringify([{
        productId: 31, name: 'Stoneware Pour-Over Set', price: 58, quantity: 1,
        image: '/products/theo-stoneware-pour-over-set.webp', origin: 'manual', addedAt: 1,
      }]))
    }
  }, { persona: ANNA, signedIn, overlay, cart })
}

/** Anna asks from the home bar; the page fills with her result and the dock answers. */
export async function askAnna(page: Page, { turn, question = ANNA_QUESTION }: { turn?: object[]; question?: string } = {}) {
  await visit(page)
  await stubStorefront(page, { turn })
  await page.goto('/')
  const ask = page.getByTestId('pellier-hero-search')
  await ask.fill(question)
  await ask.press('Enter')
  await expect(page.getByTestId('results-grid')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('chat-drawer').getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
}

export interface Surface {
  name: string
  /** A page captures whole; a drawer, dialog or overlay captures the viewport. */
  fullPage: boolean
  open: (page: Page) => Promise<void>
}

export const SURFACES: Surface[] = [
  {
    name: 'home-signed-out',
    fullPage: true,
    open: async (page) => {
      await visit(page, { signedIn: false })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/')
      await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
    },
  },
  {
    name: 'home-welcome',
    fullPage: false,
    open: async (page) => {
      await visit(page, { signedIn: false, overlay: true })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/')
      await expect(page.getByRole('dialog', { name: 'Begin with the edit.' })).toBeVisible()
    },
  },
  {
    name: 'about',
    fullPage: true,
    open: async (page) => {
      await visit(page)
      await stubStorefront(page)
      await page.goto('/about')
      await expect(page.getByTestId('editorial-brief')).toBeVisible()
    },
  },
  {
    name: 'storyboard',
    fullPage: true,
    open: async (page) => {
      await visit(page)
      await stubStorefront(page)
      await page.goto('/storyboard')
      await expect(page.getByTestId('field-notes')).toBeVisible()
    },
  },
  {
    name: 'product',
    fullPage: true,
    open: async (page) => {
      await visit(page)
      await stubStorefront(page)
      await page.goto('/product/31')
      await expect(page.getByTestId('product-detail-name')).toHaveText('Stoneware Pour-Over Set')
      await expect(page.getByTestId('product-availability')).toHaveAttribute('data-state', 'read')
    },
  },
  {
    name: 'sign-in',
    fullPage: true,
    open: async (page) => {
      await visit(page, { signedIn: false })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/signin')
      await expect(page.getByTestId('pellier-signin')).toBeVisible()
    },
  },
  {
    name: 'sign-in-operator',
    fullPage: true,
    open: async (page) => {
      await visit(page, { signedIn: false })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/signin?workspace=operator')
      await expect(page.getByTestId('pellier-signin')).toBeVisible()
    },
  },
  {
    name: 'operator',
    fullPage: true,
    open: async (page) => {
      await page.addInitScript(() => {
        sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
        localStorage.setItem('pellier-auth-session:staff', '1')
        localStorage.removeItem('pellier-theme')
      })
      await stubOperator(page)
      await page.goto('/operator')
      await expect(page.getByTestId('operator-book')).toBeVisible()
      await page.getByTestId('operator-client-jessica').click()
      await expect(page.getByTestId('operator-record')).toBeVisible()
      await expect(page.getByTestId('operator-order-301')).toContainText('Returned')
    },
  },
  {
    name: 'ask-pellier-builder',
    fullPage: false,
    open: async (page) => {
      await askAnna(page)
      const drawer = page.getByTestId('chat-drawer')
      await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
      await drawer.getByTestId('turn-fold').click()
      await expect(drawer.getByTestId('ranking-summary')).toBeVisible()
    },
  },
  {
    name: 'results',
    fullPage: true,
    open: async (page) => {
      await askAnna(page)
    },
  },
  {
    name: 'results-builder',
    fullPage: true,
    open: async (page) => {
      await askAnna(page)
      await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
      await expect(page.getByTestId('results-view').getByTestId('ranking-panel')).toBeVisible()
    },
  },
  {
    name: 'cart',
    fullPage: false,
    open: async (page) => {
      await visit(page, { cart: true })
      await stubStorefront(page)
      await page.goto('/')
      await expect(page.getByTestId('bag-count')).toHaveText('1')
      await page.getByTestId('sticky-header').getByRole('button', { name: 'Bag' }).click()
      await expect(page.getByRole('dialog', { name: /bag/i })).toContainText('Stoneware Pour-Over Set')
    },
  },
]
