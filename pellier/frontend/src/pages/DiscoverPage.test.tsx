/**
 * DiscoverPage tests - minimal `/discover` index route.
 *
 * Validates Requirements 1.13.2, 1.13.3, 1.13.4.
 *
 * Coverage (both auth states):
 *   - Header always renders with Discover in the ink-highlighted
 *     current-page state (Req 1.13.4).
 *   - Signed out: the sign-in CTA with the exact
 *     `DISCOVER_PAGE_SIGNED_OUT` copy renders; the personalized
 *     product grid does NOT render (Req 1.13.2).
 *   - Signed in: the personalized product grid renders together with
 *     the same `Coming soon - ...` editorial line as the Storyboard
 *     route (Req 1.13.2).
 *   - Copy rules from Req 1.12 are respected by relying on copy.ts
 *     as the single source of truth (Req 1.13.3).
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// --- Mocks --------------------------------------------------------------

// useAuth - controlled per-test via the `mockAuth` variable.
let mockAuth: {
  user: { sub: string; email: string; givenName?: string } | null
  isAuthenticated: boolean
  login: () => void
} = {
  user: null,
  isAuthenticated: false,
  login: vi.fn(),
}
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockAuth.user,
    isAuthenticated: mockAuth.isAuthenticated,
    accessToken: null,
    login: mockAuth.login,
    logout: vi.fn(),
    loading: false,
    preferences: null,
    prefsVersion: 0,
  }),
}))

vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({
    items: [],
    setCartOpen: vi.fn(),
  }),
}))

// CommandPill is part of site chrome and gates on persona for memory
// scoping; mock a truthy persona so the floating pill renders in both
// auth states under test.
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#1f1410',
      customer_id: 'C-MARCO',
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
    openModal: vi.fn(),
    closeModal: vi.fn(),
    chatSurface: 'drawer',
    toggleDrawer: vi.fn(),
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

import DiscoverPage from './DiscoverPage'
import { DISCOVER_PAGE_COMING_SOON, DISCOVER_PAGE_SIGNED_OUT } from '../copy'

const LIVE_CATALOG = [
  {
    id: 11,
    brand: 'Pellier',
    name: 'Italian Linen Camp Shirt',
    color: 'Indigo',
    price: 148,
    rating: 4.8,
    reviewCount: 91,
    category: 'Clothing',
    imageUrl: '/products/marco-linen-camp-shirt-indigo.webp',
    tags: ['linen', 'travel'],
  },
]

/**
 * DiscoverPage nests `<Header>` which renders a `<Link to="/workshop">`,
 * so every render needs a router ancestor. MemoryRouter is the minimal
 * wrapper — the test doesn't care about navigation behavior.
 */
function renderDiscover(ui: ReactElement = <DiscoverPage />) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

beforeEach(() => {
  mockAuth = {
    user: null,
    isAuthenticated: false,
    login: vi.fn(),
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIVE_CATALOG), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => vi.unstubAllGlobals())

// --- Tests --------------------------------------------------------------

describe('DiscoverPage - header current-page state (Req 1.13.4)', () => {
  it('renders the sticky header in both auth states', () => {
    // Signed out — header renders; "Discover" is no longer a nav item
    // in the redesigned header, so no nav item is highlighted.
    const { unmount } = renderDiscover()
    expect(screen.getByTestId('sticky-header')).toBeInTheDocument()
    unmount()

    // Signed in.
    mockAuth = {
      user: { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' },
      isAuthenticated: true,
      login: vi.fn(),
    }
    renderDiscover()
    expect(screen.getByTestId('sticky-header')).toBeInTheDocument()
  })
})

describe('DiscoverPage - signed out variant (Req 1.13.2)', () => {
  it('renders the sign-in prompt with the exact copy from copy.ts', () => {
    renderDiscover()

    const prompt = screen.getByTestId('discover-signin-prompt')
    expect(prompt).toBeInTheDocument()
    expect(screen.getByTestId('discover-signin-copy')).toHaveTextContent(
      DISCOVER_PAGE_SIGNED_OUT,
    )

    // Sign-in CTA button is present.
    expect(screen.getByTestId('discover-signin-cta')).toBeInTheDocument()
  })

  it('does not render the personalized product grid when signed out', () => {
    renderDiscover()
    expect(screen.queryByTestId('product-grid')).not.toBeInTheDocument()
    expect(screen.queryByTestId('discover-coming-soon')).not.toBeInTheDocument()
  })

  it('wires the sign-in CTA to useAuth().login', () => {
    const login = vi.fn()
    mockAuth = { user: null, isAuthenticated: false, login }

    renderDiscover()

    const cta = screen.getByTestId('discover-signin-cta')
    cta.click()
    expect(login).toHaveBeenCalledTimes(1)
  })
})

describe('DiscoverPage - signed in variant (Req 1.13.2, 1.13.3)', () => {
  beforeEach(() => {
    mockAuth = {
      user: { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' },
      isAuthenticated: true,
      login: vi.fn(),
    }
  })

  it('renders the live product grid plus the coming-soon line', async () => {
    renderDiscover()

    expect(await screen.findByTestId('product-grid')).toBeInTheDocument()
    expect(screen.getByTestId('product-card-11')).toBeInTheDocument()

    // Same coming-soon editorial line as the Storyboard page.
    const line = screen.getByTestId('discover-coming-soon')
    expect(line).toBeInTheDocument()
    expect(line).toHaveTextContent(DISCOVER_PAGE_COMING_SOON)

    // The sign-in prompt is absent in this state.
    expect(
      screen.queryByTestId('discover-signin-prompt'),
    ).not.toBeInTheDocument()
  })

  it('shows an explicit unavailable state instead of a static catalog', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 503 })),
    )

    renderDiscover()

    expect(
      await screen.findByTestId('discover-catalog-unavailable'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('product-grid')).not.toBeInTheDocument()
  })
})

describe('DiscoverPage - site chrome (Req 1.13.2)', () => {
  it('renders the header, footer, and CommandPill in both auth states', () => {
    // Signed out.
    const { unmount } = renderDiscover()
    expect(screen.getByTestId('sticky-header')).toBeInTheDocument()
    expect(screen.getByTestId('footer')).toBeInTheDocument()
    expect(screen.getByTestId('command-pill')).toBeInTheDocument()
    unmount()

    // Signed in.
    mockAuth = {
      user: { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' },
      isAuthenticated: true,
      login: vi.fn(),
    }
    renderDiscover()
    expect(screen.getByTestId('sticky-header')).toBeInTheDocument()
    expect(screen.getByTestId('footer')).toBeInTheDocument()
    expect(screen.getByTestId('command-pill')).toBeInTheDocument()
  })
})
