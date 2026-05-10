/**
 * AuthModal - Challenge 9.4a surface.
 *
 * Validates Requirement 2.6.6 (auth modal half) and the
 * `storefront.md` "Auth modal (entry point)" spec.
 *
 * Contract (per storefront.md):
 *   - Centered cream rounded-3xl card over a glass backdrop-blur overlay.
 *   - Header row: B mark + "Welcome to Pellier" + subheader
 *     "Sign in for a storefront built for you".
 *   - Body: `PERSONALIZED VISIONS` eyebrow + italic Fraunces headline
 *     "Let the storefront find you.".
 *   - Three provider buttons: `Continue with Google`, `Continue with Apple`,
 *     `Continue with email`. Each calls `redirectToSignIn(<provider>)`
 *     with the current URL passed through as `returnTo` so the user lands
 *     back where they started after Cognito Hosted UI.
 *   - Disclaimer line + `Secured by AgentCore Identity` 10px mono footer
 *     with shield icon and `v2.4` version stamp.
 *
 * Visibility is coordinated by UIContext - the modal renders only when
 * `activeModal === 'auth'` (Task 4.1). Escape + backdrop click both close
 * via `closeModal()`, and the global Escape handler in UIProvider provides
 * a safety net.
 *
 * When opened from the chooser route (`/signin?returnTo=...` - handled by
 * `openSignInChooser` in utils/auth.ts) ALL three providers are visible
 * and none is preselected, so a user who originally signed in with Google
 * is never silently forced into email/password during a re-auth.
 */

import { useEffect } from 'react'

import { AUTH_MODAL } from '../copy'
import { useUI } from '../contexts/UIContext'
import { redirectToSignIn, type SignInProvider } from '../utils/auth'

// === CHALLENGE 9.4: START ===
// --- Design tokens (storefront.md) ---------------------------------------
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'

const INTER_STACK = 'Inter, system-ui, sans-serif'
const FRAUNCES_STACK = 'Fraunces, Georgia, serif'
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
        background: CREAM,
        color: INK,
        border: `1px solid ${INK_QUIET}`,
        fontFamily: INTER_STACK,
        fontSize: 14,
        fontWeight: 500,
        letterSpacing: '0.02em',
        cursor: 'pointer',
        transition:
          'background 180ms ease-out, color 180ms ease-out, border-color 180ms ease-out, transform 120ms ease-out',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = INK
        e.currentTarget.style.color = CREAM
        e.currentTarget.style.borderColor = INK
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = CREAM
        e.currentTarget.style.color = INK
        e.currentTarget.style.borderColor = INK_QUIET
      }}
    >
      {label}
    </button>
  )
}

export default function AuthModal() {
  const { activeModal, closeModal } = useUI()
  const isOpen = activeModal === 'auth'

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
      onClick={closeModal}
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
        data-testid="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 440,
          background: CREAM,
          borderRadius: 24,
          padding: '32px 32px 20px 32px',
          boxShadow:
            '0 24px 60px rgba(45, 24, 16, 0.32), 0 4px 12px rgba(45, 24, 16, 0.2)',
          fontFamily: INTER_STACK,
          color: INK,
        }}
      >
        {/* Header: B mark + title + subtitle */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, textAlign: 'center' }}>
          <span
            data-testid="auth-modal-b-mark"
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              borderRadius: '50%',
              background: INK,
              color: CREAM,
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 20,
              lineHeight: 1,
            }}
          >
            B
          </span>
          <h2
            id="auth-modal-title"
            data-testid="auth-modal-header"
            style={{
              margin: 0,
              fontFamily: FRAUNCES_STACK,
              fontSize: 24,
              fontWeight: 500,
              color: INK,
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
              color: INK_SOFT,
              lineHeight: 1.45,
            }}
          >
            {AUTH_MODAL.SUBHEADER}
          </p>
        </div>

        {/* Body eyebrow + italic headline */}
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, textAlign: 'center' }}>
          <span
            data-testid="auth-modal-eyebrow"
            style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: '0.14em',
              color: INK_SOFT,
            }}
          >
            {AUTH_MODAL.EYEBROW}
          </span>
          <span
            data-testid="auth-modal-italic-headline"
            style={{
              fontFamily: FRAUNCES_STACK,
              fontStyle: 'italic',
              fontSize: 22,
              color: INK,
              lineHeight: 1.25,
            }}
          >
            {AUTH_MODAL.ITALIC_HEADLINE}
          </span>
        </div>

        {/* Three provider buttons - all visible, none preselected */}
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <ProviderButton
            provider="google"
            label={AUTH_MODAL.BUTTON_GOOGLE}
            testId="auth-modal-button-google"
            onClick={go('google')}
          />
          <ProviderButton
            provider="apple"
            label={AUTH_MODAL.BUTTON_APPLE}
            testId="auth-modal-button-apple"
            onClick={go('apple')}
          />
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
            color: INK_SOFT,
            lineHeight: 1.45,
          }}
        >
          {AUTH_MODAL.DISCLAIMER}
        </p>

        {/* Footer strip: shield + AgentCore Identity + version */}
        <div
          data-testid="auth-modal-footer"
          style={{
            marginTop: 18,
            paddingTop: 14,
            borderTop: `1px solid ${CREAM_WARM}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            color: INK_QUIET,
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
          <span style={{ color: INK_QUIET }}>{AUTH_MODAL.VERSION}</span>
        </div>
      </div>
    </div>
  )
}
// === CHALLENGE 9.4: END ===
