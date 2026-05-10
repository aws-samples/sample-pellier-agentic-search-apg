/**
 * StoryboardPage tests - minimal `/storyboard` index route.
 *
 * Validates Requirements 1.13.1, 1.13.3, 1.13.4.
 *
 * Coverage:
 *   - Header renders with Storyboard in the ink-highlighted
 *     current-page state (Req 1.13.4).
 *   - The 3-card Storyboard grid renders verbatim from copy.ts
 *     (Req 1.13.1 / reuse of Req 1.9).
 *   - The `Coming soon - the full editorial hub arrives with the
 *     next Edit.` editorial line renders in italic Fraunces
 *     (Req 1.13.1).
 *   - Footer and CommandPill render so the chrome matches the home
 *     page (Req 1.13.1).
 *
 * Context providers (AuthContext, CartContext, UIContext) are mocked
 * at the module level so the test focuses on the page composition
 * rather than the full provider chain.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { TEST_ROUTER_FUTURE_FLAGS } from '../test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// --- Mocks --------------------------------------------------------------

// useAuth - Storyboard page does not read auth, but Header does via the
// AccountButton child. Default to signed out.
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

// useCart - Header reads cart items for the bag badge; return an empty bag.
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({
    items: [],
    setCartOpen: vi.fn(),
  }),
}))

// usePersona - Header uses the persona pill.
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: null,
    switchPersona: vi.fn(),
    signOut: vi.fn(),
    switching: false,
  }),
}))

// useUI - CommandPill reads toggleConcierge + activeModal.
const toggleConcierge = vi.fn()
vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({
    activeModal: null,
    openModal: vi.fn(),
    closeModal: vi.fn(),
    toggleConcierge,
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

import StoryboardPage from './StoryboardPage'
import { STORYBOARD_TEASERS } from '../copy'

/**
 * StoryboardPage nests `<Header>` which renders a `<Link to="/workshop">`,
 * so every render needs a router ancestor. MemoryRouter is the minimal
 * wrapper — the test doesn't care about navigation behavior.
 */
function renderStoryboard(ui: ReactElement = <StoryboardPage />) {
  return render(<MemoryRouter future={TEST_ROUTER_FUTURE_FLAGS}>{ui}</MemoryRouter>)
}

beforeEach(() => {
  toggleConcierge.mockClear()
})

// --- Tests --------------------------------------------------------------

describe('StoryboardPage - header current-page state (Req 1.13.4)', () => {
  it('renders the sticky header with Stories in the current-page ink state', () => {
    renderStoryboard()

    const storiesNav = screen.getByRole('button', { name: 'Stories' })
    expect(storiesNav).toHaveAttribute('data-current', 'true')
    expect(storiesNav).toHaveAttribute('aria-current', 'page')

    // Sanity: the other nav items are not highlighted.
    expect(screen.getByRole('button', { name: 'Shop' })).toHaveAttribute(
      'data-current',
      'false',
    )
    expect(screen.getByRole('button', { name: 'About' })).toHaveAttribute(
      'data-current',
      'false',
    )
  })
})

describe('StoryboardPage - 3-card storyboard grid (Req 1.13.1)', () => {
  it('renders the reused StoryboardTeaser with all 3 cards', () => {
    renderStoryboard()

    // The teaser section is present.
    const teaser = screen.getByTestId('storyboard-teaser')
    expect(teaser).toBeInTheDocument()

    // 3 cards, not 1 (never collapse into a single editorial block).
    // Scope to the teaser region so Footer `<li>` elements do not leak
    // into the listitem count.
    const cards = within(teaser).getAllByRole('listitem')
    expect(cards).toHaveLength(3)

    // Spot-check the three authored eyebrows appear.
    STORYBOARD_TEASERS.forEach((_card, i) => {
      expect(
        screen.getByTestId(`storyboard-card-${i}`),
      ).toBeInTheDocument()
    })
  })
})

describe('StoryboardPage - Field Notes essay surface', () => {
  it('renders the FieldNotes section with four essays', () => {
    renderStoryboard()

    // The section mounts and carries four field notes, one per
    // persona archetype (editorial + Marco + Anna + Theo).
    const section = screen.getByTestId('field-notes')
    expect(section).toBeInTheDocument()
    for (let i = 0; i < 4; i++) {
      expect(screen.getByTestId(`field-note-${i}`)).toBeInTheDocument()
    }
  })

  it('no longer renders the old coming-soon placeholder line', () => {
    renderStoryboard()
    // The ComingSoonLine placeholder has been replaced by FieldNotes.
    expect(screen.queryByTestId('storyboard-coming-soon')).not.toBeInTheDocument()
  })
})

describe('StoryboardPage - site chrome (Req 1.13.1)', () => {
  it('renders the Footer and floating CommandPill alongside the header', () => {
    renderStoryboard()

    expect(screen.getByTestId('sticky-header')).toBeInTheDocument()
    expect(screen.getByTestId('footer')).toBeInTheDocument()
    expect(screen.getByTestId('command-pill')).toBeInTheDocument()
  })
})
