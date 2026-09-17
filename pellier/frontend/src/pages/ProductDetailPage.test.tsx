/**
 * ProductDetailPage tests — `/product/:productId`.
 *
 * The contract under test is the live Aurora read and, above all, its honesty
 * rules:
 *
 *   - The page holds a loading frame until Aurora supplies the piece. It does
 *     not paint a browser fixture whose price or stock could be stale.
 *   - Aurora supplies copy, availability, and the related live catalog rows.
 *   - A null availability read renders as an explicit "not read" and NEVER
 *     as zero stock. An unavailable read is distinct from a missing product.
 *   - Siblings come from the live catalog response, not the active profile's
 *     browser fixture.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// --- Mocks --------------------------------------------------------------

const addToCart = vi.fn()
const openDrawerWithQuery = vi.fn()
const openModal = vi.fn()

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    accessToken: null,
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
    preferences: null,
    prefsVersion: 0,
  }),
}))

vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({ items: [], addToCart, setCartOpen: vi.fn() }),
}))

// Anna is the active profile on purpose: the pieces under test belong to
// other edits, which is what proves siblings resolve from the piece.
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: {
      id: 'anna',
      display_name: 'Anna',
      avatar_initial: 'A',
      avatar_color: '#1f1410',
      customer_id: 'C-ANNA',
      role_tag: 'shopper',
      stats: { visits: 0, orders: 0, last_seen_days: null },
    },
    switchPersona: vi.fn(),
    signOut: vi.fn(),
    switching: false,
  }),
}))

vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({
    activeModal: null,
    openModal,
    closeModal: vi.fn(),
    chatSurface: 'drawer',
    setChatSurface: vi.fn(),
    toggleDrawer: vi.fn(),
    openDrawerWithQuery,
    pendingConciergeQuery: null,
    consumePendingQuery: vi.fn(),
    comparisonProducts: [],
    openComparison: vi.fn(),
    openChat: vi.fn(),
    announcementDismissed: {
      legacy: false,
      search: false,
      agentic: false,
      production: false,
    },
    dismissAnnouncement: vi.fn(),
  }),
}))

import ProductDetailPage from './ProductDetailPage'
import { PRODUCT_DETAIL } from '../copy'

// ProductCard's reveal observer needs the global in jsdom.
class NoopIntersectionObserver {
  readonly root: Element | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = [0]
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

/** A representative live catalog row. Test data remains inside the API stub. */
const SUBJECT = {
  id: 11,
  brand: 'Pellier Editions',
  name: 'Italian Linen Camp Shirt',
  color: 'Indigo',
  price: 148,
  rating: 4.8,
  reviewCount: 91,
  category: 'Tops',
  imageUrl: '/products/marco-linen-camp-shirt-indigo.webp',
  badge: 'EDITOR’S PICK',
  tags: ['linen', 'travel', 'summer'],
}

const CATALOG = [
  SUBJECT,
  {
    id: 12,
    brand: 'Pellier Editions',
    name: 'Relaxed Drawstring Trousers',
    color: 'Oat',
    price: 138,
    rating: 4.7,
    reviewCount: 73,
    category: 'Trousers',
    imageUrl: '/products/marco-linen-drawstring-trousers-oat.webp',
    badge: null,
    tags: ['linen', 'travel', 'summer'],
  },
  {
    id: 13,
    brand: 'Pellier Editions',
    name: 'Canvas Dopp Kit',
    color: 'Olive',
    price: 74,
    rating: 4.6,
    reviewCount: 45,
    category: 'Accessories',
    imageUrl: '/products/marco-canvas-dopp-kit-olive.webp',
    badge: null,
    tags: ['travel', 'utility'],
  },
  {
    id: 14,
    brand: 'Pellier Editions',
    name: 'Merino Travel Socks',
    color: 'Charcoal',
    price: 38,
    rating: 4.9,
    reviewCount: 120,
    category: 'Accessories',
    imageUrl: '/products/marco-merino-travel-socks-charcoal.webp',
    badge: null,
    tags: ['travel', 'merino'],
  },
]

interface DetailPayload {
  description?: string | null
  availability?: {
    onHand: number
    warehouses: Array<{
      warehouseId: string
      name: string
      city: string
      quantity: number
      shipWindowMin?: number | null
      shipWindowMax?: number | null
    }>
  } | null
  [key: string]: unknown
}

/**
 * Route `/api/products/:id` to a supplied payload and answer every other
 * request benignly, so unrelated chrome fetches cannot fail a test.
 */
function stubFetch(
  handler: (id: string) => Response | Promise<Response>,
  catalog: typeof CATALOG | (() => Response | Promise<Response>) = CATALOG,
) {
  const impl = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : String(input)
    const match = /\/api\/products\/(\w+)/.exec(url)
    if (match) return handler(match[1])
    if (url.endsWith('/api/products')) return typeof catalog === 'function' ? catalog() : jsonResponse(catalog)
    return new Response('[]', { status: 200 })
  })
  vi.stubGlobal('fetch', impl)
  return impl
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function detailPayload(overrides: DetailPayload = {}): DetailPayload {
  return {
    id: SUBJECT.id,
    brand: SUBJECT.brand,
    name: SUBJECT.name,
    color: SUBJECT.color,
    price: SUBJECT.price,
    rating: SUBJECT.rating,
    reviewCount: SUBJECT.reviewCount,
    category: 'Tops',
    imageUrl: SUBJECT.imageUrl,
    badge: SUBJECT.badge ?? null,
    tags: SUBJECT.tags,
    description: 'Cut from Italian linen with a relaxed camp collar.',
    availability: {
      onHand: 42,
      warehouses: [
        {
          warehouseId: 'BK-01',
          name: 'Brooklyn',
          city: 'Brooklyn, NY',
          quantity: 20,
          shipWindowMin: 1,
          shipWindowMax: 2,
        },
        {
          warehouseId: 'ATX-02',
          name: 'Austin',
          city: 'Austin, TX',
          quantity: 22,
          shipWindowMin: 2,
          shipWindowMax: 4,
        },
      ],
    },
    ...overrides,
  }
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/product/:productId" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', NoopIntersectionObserver)
  addToCart.mockReset()
  openDrawerWithQuery.mockReset()
  openModal.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// --- Live read ----------------------------------------------------------

describe('ProductDetailPage — live catalog read', () => {
  it('holds a loading frame until the Aurora read resolves', () => {
    stubFetch(() => new Promise<Response>(() => {}))

    renderAt(`/product/${SUBJECT.id}`)

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    expect(screen.queryByTestId('product-detail-name')).toBeNull()
  })

  it('lists siblings from the live catalog response, not the active profile', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    const siblings = await screen.findByTestId('product-detail-siblings')
    const liveIds = new Set(CATALOG.map(p => p.id))
    const rendered = Array.from(
      siblings.querySelectorAll('[data-testid^="product-card-"]'),
    )
      .map(node => node.getAttribute('data-testid'))
      .filter((id): id is string => /^product-card-\d+$/.test(id ?? ''))
      .map(id => Number(id.replace('product-card-', '')))

    expect(rendered.length).toBeGreaterThan(0)
    for (const id of rendered) {
      expect(liveIds.has(id)).toBe(true)
      expect(id).not.toBe(SUBJECT.id)
    }
  })
})

// --- Aurora layer -------------------------------------------------------

describe('ProductDetailPage — Aurora layer', () => {
  it('only advertises responsive derivatives that are shipped', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    const image = await screen.findByRole('img', { name: SUBJECT.name })
    const picture = image.closest('picture')
    const sourceSets = [
      image.getAttribute('srcset'),
      ...Array.from(picture?.querySelectorAll('source') ?? []).map(source =>
        source.getAttribute('srcset'),
      ),
    ].filter((value): value is string => Boolean(value))

    expect(sourceSets).not.toHaveLength(0)
    expect(sourceSets.every(sourceSet => sourceSet.includes('-960.'))).toBe(true)
    expect(sourceSets.every(sourceSet => !sourceSet.includes('-1440.'))).toBe(true)
  })

  it('renders catalog copy and per-warehouse stock once the read lands', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    expect(await screen.findByTestId('product-description')).toHaveTextContent(
      'Cut from Italian linen with a relaxed camp collar.',
    )
    expect(screen.getByTestId('product-on-hand')).toHaveTextContent('42')
    expect(screen.getByTestId('product-availability')).toHaveAttribute(
      'data-state',
      'read',
    )
    expect(screen.getByTestId('product-availability-source')).toHaveTextContent(
      PRODUCT_DETAIL.AVAILABILITY_SOURCE,
    )

    const brooklyn = screen.getByTestId('product-warehouse-BK-01')
    expect(brooklyn).toHaveTextContent('Brooklyn')
    expect(brooklyn).toHaveTextContent('20')
    expect(brooklyn).toHaveTextContent(PRODUCT_DETAIL.shipWindow(1, 2))
  })

  it('prints each catalog signal distinctly', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    const signals = await screen.findByTestId('product-detail-signals')
    const labels = Array.from(signals.children).map(node =>
      node.textContent?.trim(),
    )
    // The friendly label mode collapses every `tag.match` entry onto one
    // vocabulary label, which rendered four identical chips.
    expect(new Set(labels).size).toBe(labels.length)
    expect(labels[0]).toContain(SUBJECT.tags[0])
    // A shopper reads the tag itself, never the catalog signal's internal name.
    expect(labels.join(' ')).not.toContain('tag.match')
  })

  it('opens an enlarged view of the piece and closes it on Escape', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    const zoom = await screen.findByTestId('product-detail-zoom')
    await userEvent.click(zoom)
    expect(screen.getByTestId('product-detail-zoom-dialog')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByTestId('product-detail-zoom-dialog')).not.toBeInTheDocument()
  })

  it('sets the piece name in the editorial display voice', async () => {
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    const name = await screen.findByTestId('product-detail-name')
    // index.css forces `.font-display` to sans on every Pellier surface; the
    // product title opts back into Fraunces through its own class.
    expect(name).toHaveClass('pellier-product-title')
  })

  it('requests the piece by its catalog id', async () => {
    const impl = stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    await screen.findByTestId('product-description')
    const urls = impl.mock.calls.map(call => String(call[0]))
    expect(urls).toContain(`/api/products/${SUBJECT.id}`)
  })
})

// --- Explicit degraded states ------------------------------------------

describe('ProductDetailPage — a failed read never fabricates stock', () => {
  it('renders an explicit unavailable state when the product read fails', async () => {
    stubFetch(() => Promise.reject(new Error('network down')))

    renderAt(`/product/${SUBJECT.id}`)

    expect(
      await screen.findByTestId('product-detail-unavailable'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('product-on-hand')).toBeNull()
  })

  it('offers a retry after a service failure without claiming the product is missing', async () => {
    const user = userEvent.setup()
    let available = false
    stubFetch(() => available ? jsonResponse(detailPayload()) : new Response('', { status: 503 }))
    renderAt(`/product/${SUBJECT.id}`)
    expect(await screen.findByTestId('product-detail-unavailable')).toBeInTheDocument()
    expect(screen.queryByText(PRODUCT_DETAIL.NOT_FOUND_TITLE)).not.toBeInTheDocument()
    available = true
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('product-detail-name')).toHaveTextContent(SUBJECT.name)
    expect(screen.queryByTestId('product-detail-unavailable')).not.toBeInTheDocument()
  })

  it.each(['failed', 'pending'])('keeps the product usable when the related collection is %s', async (state) => {
    stubFetch(() => jsonResponse(detailPayload()), () => state === 'failed'
      ? Promise.reject(new Error('related collection unavailable'))
      : new Promise<Response>(() => {}))
    renderAt(`/product/${SUBJECT.id}`)
    expect(await screen.findByTestId('product-detail-name')).toHaveTextContent(SUBJECT.name)
    expect(screen.getByTestId('product-detail-add')).toBeEnabled()
    expect(screen.queryByTestId('product-detail-unavailable')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: PRODUCT_DETAIL.MORE_HEADING })).not.toBeInTheDocument()
  })

  it('declares inventory unread when availability comes back null', async () => {
    stubFetch(() => jsonResponse(detailPayload({ availability: null })))

    renderAt(`/product/${SUBJECT.id}`)

    await screen.findByTestId('product-availability-degraded')
    expect(screen.queryByTestId('product-on-hand')).toBeNull()
  })

  it('states that catalog copy was not read rather than omitting it', async () => {
    stubFetch(() => jsonResponse(detailPayload({ description: null })))

    renderAt(`/product/${SUBJECT.id}`)

    await waitFor(() =>
      expect(
        screen.getByTestId('product-description-degraded'),
      ).toHaveTextContent(PRODUCT_DETAIL.DESCRIPTION_UNAVAILABLE),
    )
  })
})

// --- Arbitrary catalog identifiers --------------------------------------

describe('ProductDetailPage — arbitrary live catalog ids', () => {
  it('renders wholly from the live row', async () => {
    stubFetch(() =>
      jsonResponse({
        id: 10,
        brand: 'Pellier Home',
        name: 'Aurora Only Piece',
        color: 'Ivory',
        price: 120,
        rating: 4.5,
        reviewCount: 12,
        category: 'Home',
        imageUrl: '/products/fresh-olive-branch-vessel.png',
        badge: null,
        tags: ['ceramic', 'home'],
        description: 'Served entirely from the catalog row.',
        availability: { onHand: 7, warehouses: [] },
      }),
    )

    renderAt('/product/10')

    expect(await screen.findByTestId('product-detail-name')).toHaveTextContent(
      'Aurora Only Piece',
    )
    expect(screen.getByTestId('product-on-hand')).toHaveTextContent('7')
    expect(screen.getByText(PRODUCT_DETAIL.WAREHOUSE_EMPTY)).toBeInTheDocument()
  })

  it('states plainly that an unknown id is not in the edit', async () => {
    stubFetch(() => new Response('null', { status: 404 }))

    renderAt('/product/99999')

    expect(
      await screen.findByTestId('product-detail-not-found'),
    ).toBeInTheDocument()
    expect(screen.getByText(PRODUCT_DETAIL.NOT_FOUND_TITLE)).toBeInTheDocument()
  })

  it.each(['not-a-number', '11abc', '1e2'])('does not attempt a read for an invalid id: %s', async (id) => {
    const impl = stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${id}`)

    expect(
      await screen.findByTestId('product-detail-not-found'),
    ).toBeInTheDocument()
    const productReads = impl.mock.calls
      .map(call => String(call[0]))
      .filter(url => url.includes('/api/products/'))
    expect(productReads).toEqual([])
  })
})

// --- Actions ------------------------------------------------------------

describe('ProductDetailPage — actions', () => {
  it('adds the piece to the bag with its catalog identity', async () => {
    const user = userEvent.setup()
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)
    await user.click(await screen.findByTestId('product-detail-add'))

    expect(addToCart).toHaveBeenCalledWith({
      productId: SUBJECT.id,
      name: SUBJECT.name,
      price: SUBJECT.price,
      image: SUBJECT.imageUrl,
      origin: 'manual',
    })
  })

  it('seeds the shopper drawer only for a catalog question', async () => {
    const user = userEvent.setup()
    stubFetch(() => jsonResponse(detailPayload()))

    renderAt(`/product/${SUBJECT.id}`)

    await user.click(await screen.findByTestId('product-detail-ask'))
    expect(openDrawerWithQuery).toHaveBeenCalledWith(
      PRODUCT_DETAIL.askQuestion(SUBJECT.name),
    )
    expect(screen.queryByTestId('product-check-stock')).toBeNull()
  })
})
