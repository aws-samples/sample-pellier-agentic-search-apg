/**
 * Header tests — Pellier sticky header.
 *
 * Validates Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3.
 *
 * Design goals:
 *  - renders four nav items (Shop, Stories, Ask Pellier, About)
 *  - shared lowercase Pellier wordmark above the storefront controls
 *  - signed-out visitors open the same three-card persona chooser as the pill
 *  - signed-in visitors open the shared portrait-led PersonaModal
 *  - bag icon with live count badge
 *  - sticky with backdrop-filter blur
 *
 * The CartContext and PersonaContext are mocked at the module level so the
 * test stays focused on the Header's behavior without pulling in the full
 * workshop chrome.
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
  membership: 'registered' | 'circle' | 'maison'
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

const LIVE_PERSONAS = [
  {
    id: 'marco',
    display_name: 'Marco',
    role_tag: 'Returning',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a3528',
    avatar_initial: 'M',
    membership: 'maison',
    stats: { visits: 11, orders: 7, last_seen_days: 21 },
  },
  {
    id: 'anna',
    display_name: 'Anna',
    role_tag: 'Gift-giver',
    blurb: 'Live Aurora profile.',
    avatar_color: '#6b3d2a',
    avatar_initial: 'A',
    membership: 'circle',
    stats: { visits: 6, orders: 5, last_seen_days: 9 },
  },
  {
    id: 'theo',
    display_name: 'Theo',
    role_tag: 'Home + slow craft',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a4535',
    avatar_initial: 'T',
    membership: 'registered',
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
  it('renders four text nav items: Shop, Stories, Ask Pellier, About', () => {
    // 'Ask Pellier' only renders when a persona is signed in; the chat
    // surface needs a persona to scope memory.
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#1f1410',
      customer_id: 'C-MARCO',
      role_tag: 'shopper',
      membership: 'registered',
      stats: { visits: 0, orders: 0, last_seen_days: null },
    }
    renderHeader()

    const navItems = [
      screen.getByRole('link', { name: 'Shop' }),
      screen.getByRole('link', { name: 'Stories' }),
      screen.getByRole('button', { name: 'Ask Pellier' }),
      screen.getByRole('link', { name: 'About' }),
    ]
    expect(navItems).toHaveLength(4)
    expect(navItems.map((el) => el.textContent)).toEqual([
      'Shop',
      'Stories',
      'Ask Pellier',
      'About',
    ])
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

  it('links directly to Pellier Observatory without repeating the storefront name', () => {
    renderHeader()
    const labsLink = screen.getByRole('link', { name: 'Observatory' })
    expect(labsLink).toHaveTextContent('Observatory')
    expect(labsLink).toHaveAttribute('href', '/observatory')
  })

  it('keeps one Observatory destination when the mobile menu opens', () => {
    renderHeader()
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    const labsLink = screen.getByRole('link', { name: 'Observatory' })
    expect(labsLink).toHaveTextContent('Observatory')
    expect(labsLink).toHaveAttribute('href', '/observatory')
  })
})

describe('Header — persona account control', () => {
  it('uses the shared deep-maroon hover treatment for signed-out account pills', () => {
    const stylesheet = readFileSync(
      'src/index.css',
      'utf8',
    )

    expect(stylesheet).toMatch(
      /\.pellier-account-pill:hover\s*\{[\s\S]*background:\s*var\(--link-hover\)/,
    )
    expect(stylesheet).toMatch(
      /\.pellier-account-pill:hover\s*\{[\s\S]*color:\s*var\(--cream-elev\)/,
    )
  })

  it('invites a scenario choice, not a sign-in, when no persona is active', () => {
    mockPersona = null
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Select scenario')
    expect(pill).not.toHaveTextContent(/sign in/i)
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
      membership: 'maison',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Marco')
    // The Avatar primitive renders the initial
    expect(pill.textContent).toContain('M')
  })

  it('opens the shared portrait selector when signed in', async () => {
    mockPersona = {
      id: 'marco',
      display_name: 'Marco',
      avatar_initial: 'M',
      avatar_color: '#5a3528',
      customer_id: 'CUST-MARCO',
      role_tag: 'Returning',
      membership: 'maison',
      stats: { visits: 11, orders: 7, last_seen_days: 21 },
    }
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))

    expect(screen.getByTestId('persona-modal')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveAccessibleName(
      'Choose a scenario',
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
      membership: 'registered',
      stats: { visits: 8, orders: 4, last_seen_days: 14 },
    }
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

describe('Header — sticky backdrop', () => {
  it('renders with sticky positioning and backdrop blur (Req 15.3)', () => {
    renderHeader()
    const header = screen.getByTestId('sticky-header')
    expect(header.className).toContain('sticky')
    // Verify backdrop-filter is set via inline style
    expect(header.style.backdropFilter).toBe('blur(12px)')
    // Note: WebkitBackdropFilter is set in the source via React's style prop
    // but jsdom doesn't serialize vendor-prefixed CSS properties. The
    // presence of -webkit-backdrop-filter is verified by source inspection
    // and the tsc --noEmit check (the style object includes WebkitBackdropFilter).
  })
})
