/**
 * AuthModal - sign-in modal surface.
 *
 * Validates Requirement 2.6.6 (auth modal half) and the
 * `storefront.md` "Auth modal (entry point)" spec.
 *
 * Contract (per storefront.md):
 *   - Centered cream rounded-3xl card over a glass backdrop-blur overlay.
 *   - Header row: Pellier mark + "Welcome to Pellier" + subheader
 *     "Sign in for a storefront built for you".
 *   - Body: account eyebrow + Instrument Sans headline
 *     "Let the storefront find you.".
 *   - The provisioned workshop account opens Cognito-backed password sign-in.
 *     Preserve the current URL as `returnTo` after authentication.
 *   - Explain where to find the generated credentials and identify Cognito
 *     as the shopper identity provider. Social providers are not provisioned.
 *
 * Visibility is coordinated by UIContext - the modal renders only when
 * `activeModal === 'auth'` (Task 4.1). Escape + backdrop click both close
 * via `closeModal()`, and the global Escape handler in UIProvider provides
 * a safety net.
 *
 * The Storefront can open this provider chooser through UIContext.
 * The separate `/signin` route renders the dedicated Pellier password page,
 * with a link to the configured hosted sign-in methods.
 */

import { useEffect, useRef } from 'react'

import { AUTH_MODAL } from '../copy'
import { useUI } from '../contexts/UIContext'
import { redirectToSignIn, type SignInProvider } from '../utils/auth'
import { cssVar as c } from '../design/cssVars'
import { useFocusTrap } from '../shared/useFocusTrap'

// === REFERENCE: START ===
// --- Design tokens (storefront.md) ---------------------------------------

const SANS_STACK = 'var(--sans)'
const MONO_STACK =
  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'

interface ProviderButtonProps {
  provider: SignInProvider
  label: string
  testId: string
  onClick: () => void
}

function ProviderButton({ provider, label, testId, onClick }: ProviderButtonProps) {
  return (
    <button
      type="button"
      data-testid={testId}
      data-provider={provider}
      onClick={onClick}
      style={{
        width: '100%',
        padding: '14px 18px',
        borderRadius: 9999,
        background: c.bg,
        color: c.ink,
        border: `1px solid ${c.muted}`,
        fontFamily: 'var(--sans)',
        fontSize: 14,
        fontWeight: 500,
        letterSpacing: '0.02em',
        cursor: 'pointer',
        transition:
          'background 180ms ease-out, color 180ms ease-out, border-color 180ms ease-out, transform 120ms ease-out',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = c.ink
        e.currentTarget.style.color = c.bg
        e.currentTarget.style.borderColor = c.ink
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = c.bg
        e.currentTarget.style.color = c.ink
        e.currentTarget.style.borderColor = c.muted
      }}
    >
      {label}
    </button>
  )
}

export default function AuthModal() {
  const { activeModal, closeModal } = useUI()
  const isOpen = activeModal === 'auth'
  const dialogRef = useRef<HTMLDivElement | null>(null)

  // Lock body scroll while open (standard modal hygiene; UIContext already
  // handles Escape via its global keydown listener).
  useEffect(() => {
    if (!isOpen || typeof document === 'undefined') return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [isOpen])

  // This dialog claims `aria-modal="true"` below; without a focus trap that
  // claim was false -- Tab carried a keyboard user straight through to the
  // page behind it. `closeModal` also serves Escape here, matching
  // CartPanel and PersonaModal's use of the same hook.
  useFocusTrap({ containerRef: dialogRef, active: isOpen, onClose: () => closeModal() })

  if (!isOpen) return null

  // Build the returnTo from the current URL so Cognito lands the user back
  // where they started. Never include the hash (OAuth chains strip it).
  const currentReturnTo =
    typeof window === 'undefined'
      ? '/'
      : `${window.location.pathname}${window.location.search}`

  const go = (provider: SignInProvider) => () => {
    redirectToSignIn(provider, { returnTo: currentReturnTo })
  }

  return (
    <div
      data-testid="auth-modal-backdrop"
      role="presentation"
      onClick={() => closeModal()}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        background: 'rgba(45, 24, 16, 0.45)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}
    >
      <div
        ref={dialogRef}
        data-testid="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 440,
          background: c.bg,
          borderRadius: 24,
          padding: '32px 32px 20px 32px',
          boxShadow:
            '0 24px 60px rgba(45, 24, 16, 0.32), 0 4px 12px rgba(45, 24, 16, 0.2)',
          fontFamily: 'var(--sans)',
          color: c.ink,
        }}
      >
        {/* Header: Pellier mark + title + subtitle */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
          <span
            data-testid="auth-modal-mark"
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              borderRadius: '50%',
              background: c.ink,
              color: c.bg,
              fontFamily: 'var(--serif)',
              fontSize: 26,
              lineHeight: 1,
            }}
          >
            p
          </span>
          <h2
            id="auth-modal-title"
            data-testid="auth-modal-header"
            style={{
              margin: 0,
              fontFamily: SANS_STACK,
              fontSize: 24,
              fontWeight: 500,
              color: c.ink,
              letterSpacing: '-0.01em',
            }}
          >
            {AUTH_MODAL.HEADER}
          </h2>
          <p
            data-testid="auth-modal-subheader"
            style={{
              margin: 0,
              fontSize: 14,
              color: c.ink2,
              lineHeight: 1.45,
            }}
          >
            {AUTH_MODAL.SUBHEADER}
          </p>
        </div>

        {/* Body eyebrow + storefront headline */}
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, textAlign: 'center' }}>
          <span
            data-testid="auth-modal-eyebrow"
            style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: '0.14em',
              color: c.ink2,
            }}
          >
            {AUTH_MODAL.EYEBROW}
          </span>
          <span
            data-testid="auth-modal-italic-headline"
            style={{
              fontFamily: SANS_STACK,
              fontWeight: 500,
              fontSize: 22,
              color: c.ink,
              lineHeight: 1.25,
            }}
          >
            {AUTH_MODAL.ITALIC_HEADLINE}
          </span>
        </div>

        {/* Offer the account type that bootstrap actually provisions. */}
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <ProviderButton
            provider="email"
            label={AUTH_MODAL.BUTTON_EMAIL}
            testId="auth-modal-button-email"
            onClick={go('email')}
          />
        </div>

        {/* Disclaimer */}
        <p
          data-testid="auth-modal-disclaimer"
          style={{
            marginTop: 20,
            textAlign: 'center',
            fontSize: 12,
            color: c.ink2,
            lineHeight: 1.45,
          }}
        >
          {AUTH_MODAL.DISCLAIMER}
        </p>

        {/* Shopper authentication is provided by Cognito. */}
        <div
          data-testid="auth-modal-footer"
          style={{
            marginTop: 18,
            paddingTop: 14,
            borderTop: `1px solid ${c.paper}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            color: c.muted,
            fontFamily: MONO_STACK,
            fontSize: 10,
            letterSpacing: '0.04em',
          }}
        >
          <svg
            data-testid="auth-modal-shield"
            aria-hidden="true"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>{AUTH_MODAL.FOOTER}</span>
        </div>
      </div>
    </div>
  )
}
// === REFERENCE: END ===
