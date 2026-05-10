/**
 * AuthModal tests - Challenge 9.4a verification.
 *
 * Validates Requirement 2.6.6 (auth modal half) and the
 * `storefront.md` "Auth modal" spec.
 *
 * Coverage:
 *   - Modal renders only when UIContext.activeModal === 'auth'.
 *   - Structure present per storefront.md: B mark, header, subheader,
 *     eyebrow, italic headline, disclaimer, footer strip.
 *   - Three provider buttons each invoke `redirectToSignIn` with the
 *     correct provider value.
 *   - All three providers visible simultaneously (no preselection), so
 *     a user arriving via `/signin?returnTo=...` can choose freely.
 *   - Clicking the backdrop closes the modal.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AuthModal from './AuthModal'
import { AUTH_MODAL } from '../copy'
import { UIProvider, useUI } from '../contexts/UIContext'

// Stub `redirectToSignIn` so tests assert the provider argument instead of
// actually navigating. `redirectToSignIn` is imported from `utils/auth.ts`
// which is a pure module - replacing the export is enough for the click
// handlers below.
vi.mock('../utils/auth', () => ({
  redirectToSignIn: vi.fn(),
}))

// Pull the mocked reference out for assertions.
import { redirectToSignIn } from '../utils/auth'
const mockedRedirectToSignIn = vi.mocked(redirectToSignIn)

/**
 * Probe that opens/closes the auth modal so tests can drive the UIContext
 * singleton without reaching into internals.
 */
function Probe() {
  const { openModal, closeModal, activeModal } = useUI()
  return (
    <div>
      <span data-testid="active">{activeModal ?? 'none'}</span>
      <button onClick={() => openModal('auth')}>open-auth</button>
      <button onClick={() => openModal('concierge')}>open-concierge</button>
      <button onClick={closeModal}>close</button>
    </div>
  )
}

function renderModal() {
  return render(
    <UIProvider>
      <Probe />
      <AuthModal />
    </UIProvider>,
  )
}

/**
 * Install a mutable `window.location` with a known pathname + search so we
 * can assert the returnTo that AuthModal threads through to
 * `redirectToSignIn`.
 */
function installLocation(pathname = '/home', search = '?ref=hero') {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: {
      pathname,
      search,
      hash: '',
      href: `http://localhost${pathname}${search}`,
      origin: 'http://localhost',
      assign: vi.fn(),
    },
  })
}

beforeEach(() => {
  installLocation()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('AuthModal visibility (UIContext singleton)', () => {
  it('renders nothing when activeModal !== "auth"', () => {
    renderModal()

    // Nothing mounted yet.
    expect(screen.queryByTestId('auth-modal')).toBeNull()
  })

  it('mounts when UIContext.activeModal === "auth"', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-auth'))

    expect(screen.getByTestId('active')).toHaveTextContent('auth')
    expect(screen.getByTestId('auth-modal')).toBeInTheDocument()
  })

  it('unmounts when another modal takes the singleton', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('auth-modal')).toBeInTheDocument()

    await user.click(screen.getByText('open-concierge'))
    expect(screen.queryByTestId('auth-modal')).toBeNull()
  })

  it('closes when the backdrop is clicked', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('auth-modal')).toBeInTheDocument()

    await user.click(screen.getByTestId('auth-modal-backdrop'))

    expect(screen.queryByTestId('auth-modal')).toBeNull()
    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })

  it('does not close when the modal card itself is clicked', async () => {
    const user = userEvent.setup()
    renderModal()

    await user.click(screen.getByText('open-auth'))
    await user.click(screen.getByTestId('auth-modal'))

    expect(screen.getByTestId('auth-modal')).toBeInTheDocument()
  })
})

describe('AuthModal structure (storefront.md)', () => {
  it('renders the B mark, header, and subheader from copy.ts', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    expect(screen.getByTestId('auth-modal-b-mark')).toHaveTextContent('B')
    expect(screen.getByTestId('auth-modal-header')).toHaveTextContent(
      AUTH_MODAL.HEADER,
    )
    expect(screen.getByTestId('auth-modal-subheader')).toHaveTextContent(
      AUTH_MODAL.SUBHEADER,
    )
  })

  it('renders the eyebrow + italic headline', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    expect(screen.getByTestId('auth-modal-eyebrow')).toHaveTextContent(
      AUTH_MODAL.EYEBROW,
    )
    expect(screen.getByTestId('auth-modal-italic-headline')).toHaveTextContent(
      AUTH_MODAL.ITALIC_HEADLINE,
    )
  })

  it('renders the disclaimer and the 10px mono AgentCore Identity footer', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    expect(screen.getByTestId('auth-modal-disclaimer')).toHaveTextContent(
      AUTH_MODAL.DISCLAIMER,
    )

    const footer = screen.getByTestId('auth-modal-footer')
    expect(footer).toHaveTextContent(AUTH_MODAL.FOOTER)
    expect(footer).toHaveTextContent(AUTH_MODAL.VERSION)
    // 10px mono strip per storefront.md.
    expect(footer.style.fontSize).toBe('10px')
    expect(footer.style.fontFamily.toLowerCase()).toMatch(/mono/)

    // Shield icon is present for visual hygiene.
    expect(screen.getByTestId('auth-modal-shield')).toBeInTheDocument()
  })
})

describe('AuthModal provider buttons (Req 2.6.6)', () => {
  it('renders all three providers simultaneously with no preselection', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    const google = screen.getByTestId('auth-modal-button-google')
    const apple = screen.getByTestId('auth-modal-button-apple')
    const email = screen.getByTestId('auth-modal-button-email')

    expect(google).toBeInTheDocument()
    expect(apple).toBeInTheDocument()
    expect(email).toBeInTheDocument()

    // Copy matches storefront.md.
    expect(google).toHaveTextContent(AUTH_MODAL.BUTTON_GOOGLE)
    expect(apple).toHaveTextContent(AUTH_MODAL.BUTTON_APPLE)
    expect(email).toHaveTextContent(AUTH_MODAL.BUTTON_EMAIL)

    // No button carries an "active/selected" marker - they are peers.
    for (const btn of [google, apple, email]) {
      expect(btn.getAttribute('aria-pressed')).toBeNull()
      expect(btn.getAttribute('data-selected')).toBeNull()
    }
  })

  it('invokes redirectToSignIn("google") with the current URL as returnTo', async () => {
    installLocation('/discover', '?ref=hero')
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    await user.click(screen.getByTestId('auth-modal-button-google'))

    expect(mockedRedirectToSignIn).toHaveBeenCalledTimes(1)
    expect(mockedRedirectToSignIn).toHaveBeenCalledWith('google', {
      returnTo: '/discover?ref=hero',
    })
  })

  it('invokes redirectToSignIn("apple") with the current URL as returnTo', async () => {
    installLocation('/cart', '')
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    await user.click(screen.getByTestId('auth-modal-button-apple'))

    expect(mockedRedirectToSignIn).toHaveBeenCalledTimes(1)
    expect(mockedRedirectToSignIn).toHaveBeenCalledWith('apple', {
      returnTo: '/cart',
    })
  })

  it('invokes redirectToSignIn("email") with the current URL as returnTo', async () => {
    installLocation('/', '')
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    await user.click(screen.getByTestId('auth-modal-button-email'))

    expect(mockedRedirectToSignIn).toHaveBeenCalledTimes(1)
    expect(mockedRedirectToSignIn).toHaveBeenCalledWith('email', {
      returnTo: '/',
    })
  })
})
