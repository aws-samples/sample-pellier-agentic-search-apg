/**
 * Header tests — Pellier sticky header.
 *
 * Validates Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3.
 *
 * Design goals:
 *  - renders four nav items (Shop, Stories, Ask Pellier, About)
 *  - shared lowercase Pellier wordmark above the storefront controls
 *  - signed-out visitors open the shopper chooser, where choosing is a sign-in
 *  - signed-in visitors open the same portrait-led PersonaModal to switch
 *  - bag icon with live count badge
 *  - sticky with backdrop-filter blur
 *
 * The CartContext, PersonaContext and AuthContext are mocked at the module
 * level so the test stays focused on the Header's behavior without pulling in
 * the full workshop chrome. `mockSignedInAs` is the shopper session's
 * username, as `/api/auth/me` reports it.
 *
 * Header renders route links, so every render wraps in a `<MemoryRouter>`.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { UIProvider } from '../contexts/UIContext'

// --- Mocks -------------------------------------------------------------

// useCart — only `items` and `setCartOpen` are exercised by Header.
let mockCartItems: Array<{ productId: number; quantity: number }> = []
const setCartOpen = vi.fn()
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({
    items: mockCartItems,
    setCartOpen,
  }),
}))

// usePersona — Header uses the persona Avatar dropdown.
let mockPersona: {
  id: string
  display_name: string
  avatar_initial: string
  avatar_color: string
  customer_id: string
  role_tag: string
  stats: { visits: number; orders: number; last_seen_days: number | null }
} | null = null
const mockSwitchPersona = vi.fn()
const mockSignOut = vi.fn()
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: mockPersona,
    switchPersona: mockSwitchPersona,
    signOut: mockSignOut,
    switching: false,
  }),
}))

// The shopper session: the pill names it, never the edit on screen.
let mockSignedInAs: string | null = null
vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: Boolean(mockSignedInAs),
    user: mockSignedInAs ? { sub: `sub-${mockSignedInAs}`, email: '', username: mockSignedInAs } : null,
    refresh: vi.fn(),
    logout: vi.fn(),
  }),
}))

const LIVE_PERSONAS = [
  {
    id: 'marco',
    display_name: 'Marco',
    role_tag: 'Returning',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a3528',
    avatar_initial: 'M',
    stats: { visits: 11, orders: 7, last_seen_days: 21 },
  },
  {
    id: 'anna',
    display_name: 'Anna',
    role_tag: 'Gift-giver',
    blurb: 'Live Aurora profile.',
    avatar_color: '#6b3d2a',
    avatar_initial: 'A',
    stats: { visits: 6, orders: 5, last_seen_days: 9 },
  },
  {
    id: 'theo',
    display_name: 'Theo',
    role_tag: 'Home + slow craft',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a4535',
    avatar_initial: 'T',
    stats: { visits: 8, orders: 4, last_seen_days: 14 },
  },
]

// Import Header AFTER mocks so the mocked hooks are bound inside the module.
import Header from './Header'
import SurfaceNavigation from './SurfaceNavigation'

// --- Helpers -----------------------------------------------------------

function renderHeader(ui: ReactElement = <Header />) {
  return render(
    <UIProvider>
      <MemoryRouter><SurfaceNavigation />{ui}</MemoryRouter>
    </UIProvider>,
  )
}

beforeEach(() => {
  mockPersona = null
  mockSignedInAs = null
  mockCartItems = []
  setCartOpen.mockClear()
  mockSwitchPersona.mockClear()
  mockSignOut.mockClear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIVE_PERSONAS), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// --- Tests -------------------------------------------------------------

describe('Header — nav items', () => {
  it('renders three text nav items: Shop, Stories, About; Ask Pellier lives in the shared bar', () => {
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#1f1410',
      customer_id: 'C-MARCO',
      role_tag: 'shopper',
      stats: { visits: 0, orders: 0, last_seen_days: null },
    }
    renderHeader()

    const navItems = [
      screen.getByRole('link', { name: 'Shop' }),
      screen.getByRole('link', { name: 'Stories' }),
      screen.getByRole('link', { name: 'About' }),
    ]
    expect(navItems).toHaveLength(3)
    expect(navItems.map((el) => el.textContent)).toEqual(['Shop', 'Stories', 'About'])
    // One Ask Pellier entry point, in the shared bar, with the copper dot.
    const ask = screen.getByTestId('header-ask-pellier')
    expect(ask).toHaveTextContent('Ask Pellier')
    expect(ask.querySelector('.tn-dot')).not.toBeNull()
    expect(ask).toHaveAttribute('data-running', 'false')
  })

  it('renders one shared Pellier wordmark above the storefront controls', () => {
    renderHeader()
    const wordmark = screen.getByRole('link', { name: 'Pellier home' })
    expect(wordmark).toHaveTextContent('pellier')
    expect(screen.queryByTestId('wordmark')).not.toBeInTheDocument()
  })

  it('has no legacy Home/Storyboard/Discover/Account nav items', () => {
    renderHeader()
    expect(
      screen.queryByRole('button', { name: /^Home$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^Storyboard$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^Discover$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^Account$/ }),
    ).not.toBeInTheDocument()
  })

  it('applies the current-page highlight to the matching nav item', () => {
    renderHeader(<Header current="shop" />)
    const shop = screen.getByRole('link', { name: 'Shop' })
    expect(shop).toHaveAttribute('data-current', 'true')
    expect(shop).toHaveAttribute('aria-current', 'page')

    const stories = screen.getByRole('link', { name: 'Stories' })
    expect(stories).toHaveAttribute('data-current', 'false')
  })

  it('keeps the shared navigation outside the mobile menu', () => {
    renderHeader()
    expect(screen.getByRole('navigation', { name: 'Pellier surfaces' })).toBeInTheDocument()
    expect(screen.queryByTestId('mobile-menu')).not.toBeInTheDocument()
  })

})

describe('Header — persona account control', () => {
  it('styles the scenario pill from tokens only', () => {
    const stylesheet = readFileSync('src/index.css', 'utf8')

    expect(stylesheet).toMatch(
      /\.pellier-account-pill:hover\s*\{[\s\S]*?background:\s*var\(--dl-paper-2\)/,
    )
    expect(stylesheet).toMatch(
      /\.pellier-account-pill-active\s*\{[\s\S]*?background:\s*var\(--dl-ink\)/,
    )
  })

  it('invites the visitor to choose a shopper when signed out', () => {
    mockPersona = null
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Choose a shopper')
    expect(pill).not.toHaveTextContent(/scenario/i)
    expect(pill).toHaveClass('pellier-account-pill')
  })

  it('shows persona monogram and display name when signed in (Req 5.2)', () => {
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#5a3528',
      customer_id: 'CUST-MARCO',
      role_tag: 'Returning',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    mockSignedInAs = 'marco'
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Marco')
    // The Avatar primitive renders the initial
    expect(pill.textContent).toContain('M')
  })

  it('names the signed-in session, never an edit left from the previous shopper', () => {
    // Theo signed in, and opening his edit failed: Marco's edit is still on screen.
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#5a3528',
      customer_id: 'CUST-MARCO',
      role_tag: 'Returning',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    mockSignedInAs = 'theo'
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Theo')
    expect(pill).not.toHaveTextContent('Marco')
  })

  it('shows the chooser, not a leftover edit, when the shopper session is signed out', () => {
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#5a3528',
      customer_id: 'CUST-MARCO',
      role_tag: 'Returning',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    renderHeader()
    expect(screen.getByTestId('persona-pill')).toHaveTextContent('Choose a shopper')
  })

  it('opens the shared portrait selector when signed in', async () => {
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#5a3528',
      customer_id: 'CUST-MARCO',
      role_tag: 'Returning',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    mockSignedInAs = 'marco'
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))

    expect(screen.getByTestId('persona-modal')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveAccessibleName(
      'Choose a shopper',
    )
    expect(screen.queryByTestId('persona-dropdown')).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('persona-card-marco')).toBeInTheDocument()
    })
  })

  it('closes the authenticated selector from its close control', async () => {
    mockPersona = {
      id: 'theo',
      display_name: 'Theo',
      avatar_initial: 'T',
      avatar_color: '#5a4535',
      customer_id: 'CUST-THEO',
      role_tag: 'Home + slow craft',
      stats: { visits: 8, orders: 4, last_seen_days: 14 },
    }
    mockSignedInAs = 'theo'
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))
    expect(screen.getByTestId('persona-modal')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('persona-modal-close'))
    await waitFor(() => {
      expect(screen.queryByTestId('persona-modal')).not.toBeInTheDocument()
    })
  })

  it('opens the three-card persona chooser when signed out', () => {
    mockPersona = null
    renderHeader()
    expect(screen.queryByTestId('persona-modal')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('persona-pill'))

    expect(screen.getByTestId('persona-modal')).toBeInTheDocument()
    expect(screen.queryByTestId('persona-dropdown')).not.toBeInTheDocument()
  })

  it('closes the persona chooser from its close control', async () => {
    mockPersona = null
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))
    fireEvent.click(screen.getByTestId('persona-modal-close'))

    await waitFor(() => {
      expect(screen.queryByTestId('persona-modal')).not.toBeInTheDocument()
    })
  })
})

describe('Header — Bag badge', () => {
  it('does not render the count badge when the bag is empty', () => {
    mockCartItems = []
    renderHeader()
    expect(screen.queryByTestId('bag-count')).not.toBeInTheDocument()
  })

  it('renders the live count when items are present', () => {
    mockCartItems = [
      { productId: 1, quantity: 2 },
      { productId: 2, quantity: 1 },
    ]
    renderHeader()
    expect(screen.getByTestId('bag-count')).toHaveTextContent('3')
  })
})

describe('Header — sticky row', () => {
  it('owns its ground, hairline and stacking in the stylesheet, not in utilities', () => {
    renderHeader()
    const header = screen.getByTestId('sticky-header')
    expect(header.className).toBe('pellier-storefront-header')
    expect(header.getAttribute('style')).toBeNull()

    // Opaque on the page ground, the hairline beneath, above the page
    // content and below the shared bar (55) and the docked panel (51).
    const css = readFileSync('src/styles/surface-navigation.css', 'utf8')
    const start = css.indexOf('.pellier-storefront-header {')
    expect(start).toBeGreaterThan(-1)
    const rule = css.slice(start, css.indexOf('}', start))
    expect(rule).toContain('position: sticky')
    expect(rule).toContain('top: var(--pellier-chrome-height)')
    expect(rule).toContain('z-index: 40')
    expect(rule).toContain('background: var(--dl-bg)')
    expect(rule).toContain('border-bottom: 1px solid var(--dl-line)')
  })
})
