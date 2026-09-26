/**
 * AuthModal tests - sign-in modal verification.
 *
 * Validates Requirement 2.6.6 (auth modal half) and the
 * `storefront.md` "Auth modal" spec.
 *
 * Coverage:
 *   - Modal renders only when UIContext.activeModal === 'auth'.
 *   - Structure present per storefront.md: B mark, header, subheader,
 *     eyebrow, italic headline, disclaimer, footer strip.
 *   - The provisioned account button invokes `redirectToSignIn`, so
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
      <button onClick={() => openModal('drawer')}>open-drawer</button>
      <button onClick={() => closeModal()}>close</button>
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

    await user.click(screen.getByText('open-drawer'))
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

  it('identifies Cognito and the generated workshop credentials', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    expect(screen.getByTestId('auth-modal-disclaimer')).toHaveTextContent(
      AUTH_MODAL.DISCLAIMER,
    )

    const footer = screen.getByTestId('auth-modal-footer')
    expect(footer).toHaveTextContent(AUTH_MODAL.FOOTER)
    // 10px mono strip per storefront.md.
    expect(footer.style.fontSize).toBe('10px')
    expect(footer.style.fontFamily.toLowerCase()).toMatch(/mono/)

    // Shield icon is present for visual hygiene.
    expect(screen.getByTestId('auth-modal-shield')).toBeInTheDocument()
  })
})

describe('AuthModal provider buttons (Req 2.6.6)', () => {
  it('offers only the provisioned workshop account', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))
    expect(screen.getByTestId('auth-modal-button-email')).toHaveTextContent(AUTH_MODAL.BUTTON_EMAIL)
    expect(screen.queryByTestId('auth-modal-button-google')).not.toBeInTheDocument()
    expect(screen.queryByTestId('auth-modal-button-apple')).not.toBeInTheDocument()
    expect(screen.getByTestId('auth-modal-footer')).not.toHaveTextContent('AgentCore Identity')
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

describe('AuthModal focus containment', () => {
  // The dialog claims `aria-modal="true"`; a keyboard user reaching the
  // page behind it via Tab makes that claim false. Regression test for the
  // missing `useFocusTrap` wiring.
  it('keeps Tab from a provider button on Shift+Tab from the first control', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    const dialog = screen.getByTestId('auth-modal')
    const account = screen.getByTestId('auth-modal-button-email')
    account.focus()
    expect(document.activeElement).toBe(account)

    await user.tab({ shift: true })

    // Shift+Tab from the first focusable control wraps to the last one
    // inside the dialog, never out to `open-auth` or `open-drawer` behind it.
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(screen.getByText('open-auth'))
  })

  it('moves focus into the dialog when it opens', async () => {
    const user = userEvent.setup()
    renderModal()
    await user.click(screen.getByText('open-auth'))

    const dialog = screen.getByTestId('auth-modal')
    expect(dialog.contains(document.activeElement)).toBe(true)
  })
})
