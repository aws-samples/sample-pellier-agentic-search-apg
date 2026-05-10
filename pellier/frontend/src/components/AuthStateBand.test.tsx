/**
 * AuthStateBand tests — mutually exclusive band below the hero stage.
 *
 * Validates: Requirements 1.4.1, 1.4.2, 1.4.3, 1.4.4, 1.4.5 and Design
 * decision #2 (the `just_signed_in` cookie read + delete behavior).
 *
 * Coverage (the four state combinations + cookie path):
 *   1. signed out, not dismissed         → SignInStrip renders
 *   2. signed out, dismissed this session → nothing renders
 *   3. signed in + preferences           → CuratedBanner renders
 *   4. signed in + null preferences      → nothing renders; modal auto-open
 *      gated on the `just_signed_in` cookie being present.
 *
 * Plus: the cookie read/delete contract is asserted for every path:
 *   - cookie present on mount → deleted immediately
 *   - cookie absent on mount  → no delete attempt, modal not opened
 *   - cookie present but preferences non-null → modal NOT opened
 *   - cookie present + anon   → modal NOT opened (user must be signed in)
 *
 * The CartContext + LayoutContext aren't needed here; UIContext is mounted
 * live so the `openModal` call path is exercised end-to-end.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

import { UIProvider, useUI } from '../contexts/UIContext'
import type { Preferences } from '../services/types'

// --- useAuth mock -------------------------------------------------------
// Controlled per-test via `mockUser` / `mockPreferences`. Keeping the mock
// at the module boundary lets us avoid mounting AuthProvider + the JWT flow.
let mockUser: { sub: string; email: string; givenName?: string } | null = null
let mockPreferences: Preferences | null = null

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isAuthenticated: mockUser !== null,
    accessToken: null,
    login: () => {},
    logout: () => {},
    loading: false,
    preferences: mockPreferences,
  }),
}))

// Import AFTER the mock so the component resolves the mocked useAuth.
import AuthStateBand from './AuthStateBand'

// --- Test scaffolding ---------------------------------------------------

// Harness that exposes `activeModal` next to the band so tests can assert
// on the modal singleton without poking into UIContext internals.
function Harness() {
  const { activeModal } = useUI()
  return (
    <div>
      <span data-testid="active-modal">{activeModal ?? 'none'}</span>
      <AuthStateBand />
    </div>
  )
}

function renderBand() {
  return render(
    <UIProvider>
      <Harness />
    </UIProvider>,
  )
}

// Minimal document.cookie harness. jsdom's default implementation is
// append-only + read-back, which matches real browser semantics; we just
// need a clean slate between tests.
function clearAllCookies() {
  // Walk the current cookie string and expire every name with Max-Age=0.
  document.cookie.split(';').forEach(raw => {
    const trimmed = raw.trim()
    if (!trimmed) return
    const eq = trimmed.indexOf('=')
    const name = eq === -1 ? trimmed : trimmed.slice(0, eq)
    if (name) {
      document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`
    }
  })
}

function setJustSignedInCookie() {
  document.cookie = 'just_signed_in=1; path=/; SameSite=Lax'
}

beforeEach(() => {
  mockUser = null
  mockPreferences = null
  clearAllCookies()
  try {
    window.sessionStorage.clear()
  } catch {
    // jsdom always provides sessionStorage; this is just defensive.
  }
})

afterEach(() => {
  vi.restoreAllMocks()
})

// --- Signed out → nothing renders ---------------------------------------
// Personas replaced Cognito as the primary sign-in surface, so the old
// SignInStrip no longer shows. The SignInStrip component is still exported
// for any consumer that wants to mount it directly, but AuthStateBand does
// not render it for the anonymous path.
describe('AuthStateBand — signed out', () => {
  it('renders nothing when the user is signed out', () => {
    mockUser = null
    renderBand()

    expect(screen.queryByTestId('signin-strip')).not.toBeInTheDocument()
    expect(screen.queryByTestId('curated-banner')).not.toBeInTheDocument()
  })
})

// --- 1.4.3 + 1.4.5: signed-in + prefs → CuratedBanner -------------------
describe('AuthStateBand — signed in with preferences (Req 1.4.3, 1.4.5)', () => {
  beforeEach(() => {
    mockUser = { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' }
    mockPreferences = {
      vibe: ['minimal'],
      colors: ['neutral'],
      occasions: ['everyday'],
      categories: ['linen'],
    }
  })

  it('renders the CuratedBanner and not the SignInStrip', () => {
    renderBand()
    expect(screen.getByTestId('curated-banner')).toBeInTheDocument()
    expect(screen.queryByTestId('signin-strip')).not.toBeInTheDocument()
  })

  it('uses the given_name from useAuth() in the headline', () => {
    renderBand()
    expect(screen.getByTestId('curated-banner-headline')).toHaveTextContent(
      /Tailored to your preferences, Ada\./,
    )
  })

  it('includes the three pref labels in the headline, capitalized', () => {
    renderBand()
    // Top-3 ordering is vibe → categories → occasions → colors.
    const headline = screen.getByTestId('curated-banner-headline').textContent
    expect(headline).toMatch(/Minimal/)
    expect(headline).toMatch(/Linen/)
    expect(headline).toMatch(/Everyday/)
  })

  it('applies the fade-slide-up 0.6s entrance class (Req 1.4.5)', () => {
    renderBand()
    // The animation is CSS-driven; asserting on the class is the stable
    // way to validate entrance animation in jsdom where computed styles
    // from a keyframe are not available.
    expect(screen.getByTestId('curated-banner')).toHaveClass(
      'animate-fade-slide-up',
    )
  })

  it('clicking "Adjust preferences" opens the preferences modal', async () => {
    const user = userEvent.setup()
    renderBand()

    await user.click(screen.getByTestId('curated-banner-adjust'))
    expect(screen.getByTestId('active-modal')).toHaveTextContent('preferences')
  })
})

// --- 1.4.4: signed-in + null prefs → nothing rendered -------------------
describe('AuthStateBand — signed in with no preferences (Req 1.4.4)', () => {
  beforeEach(() => {
    mockUser = { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' }
    mockPreferences = null
  })

  it('renders neither band', () => {
    renderBand()
    expect(screen.queryByTestId('signin-strip')).not.toBeInTheDocument()
    expect(screen.queryByTestId('curated-banner')).not.toBeInTheDocument()
  })
})

// --- Design decision #2: just_signed_in cookie -------------------------
describe('AuthStateBand — just_signed_in cookie (Design decision #2)', () => {
  it('reads and deletes the cookie on mount, then opens the preferences modal when prefs are null', () => {
    mockUser = { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' }
    mockPreferences = null
    setJustSignedInCookie()
    expect(document.cookie).toMatch(/just_signed_in/)

    renderBand()

    // Cookie is deleted after first read.
    expect(document.cookie).not.toMatch(/just_signed_in/)
    // And the preferences modal is auto-opened for the fresh sign-in.
    expect(screen.getByTestId('active-modal')).toHaveTextContent('preferences')
  })

  it('does not open the preferences modal when the cookie is absent, even with null prefs', () => {
    mockUser = { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' }
    mockPreferences = null
    // No cookie set.

    renderBand()

    expect(document.cookie).not.toMatch(/just_signed_in/)
    expect(screen.getByTestId('active-modal')).toHaveTextContent('none')
  })

  it('does not open the preferences modal when cookie is present but prefs are non-null', () => {
    mockUser = { sub: 'abc', email: 'ada@example.com', givenName: 'Ada' }
    mockPreferences = {
      vibe: ['minimal'],
      colors: ['neutral'],
      occasions: ['everyday'],
      categories: ['linen'],
    }
    setJustSignedInCookie()

    renderBand()

    // Cookie still gets deleted (single-use flag).
    expect(document.cookie).not.toMatch(/just_signed_in/)
    // Modal stays closed; the curated banner is what the user sees.
    expect(screen.getByTestId('active-modal')).toHaveTextContent('none')
    expect(screen.getByTestId('curated-banner')).toBeInTheDocument()
  })

  it('does not open the preferences modal for an anonymous user, even with the cookie set', () => {
    mockUser = null
    mockPreferences = null
    // The cookie could linger across a sign-out in theory; guard on user.
    setJustSignedInCookie()

    renderBand()

    // Cookie gets cleaned up regardless so it doesn't misfire on a later
    // authenticated mount.
    expect(document.cookie).not.toMatch(/just_signed_in/)
    expect(screen.getByTestId('active-modal')).toHaveTextContent('none')
  })
})

// --- Guarded rerender semantics -----------------------------------------
describe('AuthStateBand — single cookie read per mount', () => {
  it('does not re-open the modal on rerender after the cookie is consumed', () => {
    mockUser = { sub: 'abc', email: 'ada@example.com' }
    mockPreferences = null
    setJustSignedInCookie()

    const { rerender } = renderBand()
    expect(screen.getByTestId('active-modal')).toHaveTextContent('preferences')

    // Simulate the UI closing the modal (e.g., user skipped). The cookie
    // has already been deleted so a rerender must not reopen it.
    act(() => {
      // Close via keyboard (UIContext Escape handler).
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    })
    expect(screen.getByTestId('active-modal')).toHaveTextContent('none')

    rerender(
      <UIProvider>
        <Harness />
      </UIProvider>,
    )
    // Important: after close + rerender, the effect must not reopen.
    expect(screen.getByTestId('active-modal')).toHaveTextContent('none')
  })
})
