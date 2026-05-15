/**
 * Header tests — Boutique sticky header (Phase 2 rebuild).
 *
 * Validates Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3.
 *
 * Design goals:
 *  - renders four nav items (Shop, Stories, Ask Pellier, About)
 *  - centered "Pellier" wordmark with circular P logo
 *  - persona Avatar dropdown replaces PersonaPill + PersonaModal
 *  - bag icon with live count badge
 *  - sticky with backdrop-filter blur
 *
 * The CartContext and PersonaContext are mocked at the module level so the
 * test stays focused on the Header's behavior without pulling in the full
 * workshop chrome.
 *
 * Header internally renders a SurfaceToggle with `<Link>` from
 * react-router-dom, so every render wraps in a `<MemoryRouter>`.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { UIProvider } from '../contexts/UIContext'
import { TEST_ROUTER_FUTURE_FLAGS } from '../test-utils'

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

// Import Header AFTER mocks so the mocked hooks are bound inside the module.
import Header from './Header'

// --- Helpers -----------------------------------------------------------

function renderHeader(ui: ReactElement = <Header />) {
  return render(
    <UIProvider>
      <MemoryRouter future={TEST_ROUTER_FUTURE_FLAGS}>{ui}</MemoryRouter>
    </UIProvider>,
  )
}

beforeEach(() => {
  mockPersona = null
  mockCartItems = []
  setCartOpen.mockClear()
  mockSwitchPersona.mockClear()
  mockSignOut.mockClear()
})

// --- Tests -------------------------------------------------------------

describe('Header — nav items', () => {
  it('renders four text nav items: Shop, Stories, Ask Pellier, About', () => {
    renderHeader()

    const navItems = screen.getAllByRole('button', {
      name: /^(Shop|Stories|Ask Pellier|About)$/,
    })
    expect(navItems).toHaveLength(4)
    expect(navItems.map((el) => el.textContent)).toEqual([
      'Shop',
      'Stories',
      'Ask Pellier',
      'About',
    ])
  })

  it('renders the Pellier wordmark centered', () => {
    renderHeader()
    const wordmark = screen.getByTestId('wordmark')
    expect(wordmark).toHaveTextContent('Pellier')
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
    const shop = screen.getByRole('button', { name: 'Shop' })
    expect(shop).toHaveAttribute('data-current', 'true')
    expect(shop).toHaveAttribute('aria-current', 'page')

    const stories = screen.getByRole('button', { name: 'Stories' })
    expect(stories).toHaveAttribute('data-current', 'false')
  })

  it('keeps the centered wordmark visible', () => {
    renderHeader()
    const wordmarkWrapper = screen.getByTestId('wordmark-wrapper')
    expect(wordmarkWrapper.className).not.toMatch(/\bhidden\b/)
  })
})

describe('Header — Persona Avatar dropdown', () => {
  it('shows "Sign in" when no persona is active (Req 5.3)', () => {
    mockPersona = null
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Sign in')
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
    renderHeader()
    const pill = screen.getByTestId('persona-pill')
    expect(pill).toHaveTextContent('Marco')
    // The Avatar primitive renders the initial
    expect(pill.textContent).toContain('M')
  })

  it('opens dropdown on click (Req 5.1)', () => {
    mockPersona = null
    renderHeader()
    expect(screen.queryByTestId('persona-dropdown')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('persona-pill'))
    expect(screen.getByTestId('persona-dropdown')).toBeInTheDocument()
  })

  it('closes dropdown on Escape (Req 5.5)', () => {
    mockPersona = null
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))
    expect(screen.getByTestId('persona-dropdown')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('persona-dropdown')).not.toBeInTheDocument()
  })

  it('closes dropdown on outside click (Req 5.5)', () => {
    mockPersona = null
    renderHeader()
    fireEvent.click(screen.getByTestId('persona-pill'))
    expect(screen.getByTestId('persona-dropdown')).toBeInTheDocument()

    // Click outside the dropdown
    fireEvent.mouseDown(document.body)
    expect(screen.queryByTestId('persona-dropdown')).not.toBeInTheDocument()
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
