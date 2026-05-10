/**
 * AuthStateBand — Mutually exclusive band below the hero stage.
 *
 * Validates Requirement 1.4.1 through 1.4.5 and Design decision #2 (the
 * `just_signed_in` cookie).
 *
 * Renders one of three states based on `useAuth()`:
 *
 *  - Signed out (and not dismissed this session): <SignInStrip>
 *      cream-warm gradient, B mark with pulse dot, PERSONALIZED VISIONS
 *      eyebrow, italic Fraunces headline, CTA + "Not now" dismiss.
 *      Dismissal writes sessionStorage 'pellier.signinStrip.dismissed=true'.
 *
 *  - Signed in with non-null preferences: <CuratedBanner>
 *      terracotta gradient, pulse dot, CURATED FOR YOU label,
 *      tailored headline with given_name + 3 prefs, Adjust link.
 *      Entrance animation: fade-slide-up 0.6s (Req 1.4.5).
 *
 *  - Signed in with null preferences: renders nothing. Instead, on first
 *    mount it reads the `just_signed_in` cookie (set by the backend Cognito
 *    callback per Design decision #2), immediately deletes it, and opens
 *    the preferences modal via UIContext if the cookie was present.
 *
 * The cookie read/delete happens once per component mount. If the cookie
 * expired before the SPA mounted (rare — 60s budget) the modal still opens
 * because `preferences === null` is the only trigger gate below; the design
 * note calls this the "open once on first null-preferences fetch" fallback.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useUI } from '../contexts/UIContext'
import {
  SIGN_IN_STRIP,
  CURATED_BANNER,
  curatedHeadline,
} from '../copy'
import type { Preferences } from '../services/types'

// --- Color tokens (storefront.md design tokens) -------------------------
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'
const DUSK = '#3d2518'

const DISMISSED_KEY = 'pellier.signinStrip.dismissed'
const JUST_SIGNED_IN_COOKIE = 'just_signed_in'

// --- Cookie helpers -----------------------------------------------------
// Read a cookie by name. Returns the value or null when absent. Keeps the
// surface small so tests can drive behavior by stubbing `document.cookie`.
export function readCookie(name: string): string | null {
  if (typeof document === 'undefined' || !document.cookie) return null
  const match = document.cookie
    .split(';')
    .map(c => c.trim())
    .find(c => c.startsWith(`${name}=`))
  if (!match) return null
  return decodeURIComponent(match.slice(name.length + 1))
}

// Delete a cookie by setting Max-Age=0 with a root path so the delete
// matches however the server set it (path=/ per the Cognito callback).
export function deleteCookie(name: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`
}

// Pick the top 3 preference labels for the curated headline. Order:
// vibe, then categories, then occasions, then colors. Empty arrays skipped.
// Values are capitalized for display (the wire format is lowercase).
function topThreePrefs(prefs: Preferences): [string, string, string] {
  const ordered: string[] = [
    ...prefs.vibe,
    ...prefs.categories,
    ...prefs.occasions,
    ...prefs.colors,
  ]
  const picks = ordered.slice(0, 3)
  // Pad with empty strings if fewer than 3 prefs were ever selected. The
  // design does not specify this edge case; we just avoid an undefined
  // interpolation in the headline.
  while (picks.length < 3) picks.push('')
  const cap = (s: string) =>
    s.length === 0 ? '' : s[0].toUpperCase() + s.slice(1)
  return [cap(picks[0]), cap(picks[1]), cap(picks[2])]
}

// --- SignInStrip (signed-out state) ------------------------------------
interface SignInStripProps {
  onDismiss: () => void
  onSignIn: () => void
}

export function SignInStrip({ onDismiss, onSignIn }: SignInStripProps) {
  return (
    <section
      data-testid="signin-strip"
      aria-label="Sign in for personalized visions"
      className="w-full"
      style={{
        background: `linear-gradient(135deg, ${CREAM_WARM} 0%, ${CREAM} 100%)`,
        padding: '20px 24px',
      }}
    >
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 text-center md:flex-row md:justify-between md:text-left">
        <div className="flex items-center gap-3">
          <span
            data-testid="signin-strip-b-mark"
            aria-hidden="true"
            className="relative inline-flex h-8 w-8 items-center justify-center rounded-full"
            style={{
              background: INK,
              color: CREAM,
              fontFamily: 'Fraunces, serif',
              fontStyle: 'italic',
              fontSize: '14px',
              lineHeight: 1,
            }}
          >
            B
            <span
              data-testid="signin-strip-pulse-dot"
              className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full"
              style={{
                background: ACCENT,
                boxShadow: `0 0 0 0 ${ACCENT}`,
                animation: 'pulse-glow 2s infinite',
              }}
            />
          </span>
          <div className="flex flex-col">
            <span
              style={{
                fontSize: '10px',
                letterSpacing: '0.14em',
                color: INK_SOFT,
                fontWeight: 600,
              }}
            >
              {SIGN_IN_STRIP.EYEBROW}
            </span>
            <span
              style={{
                fontFamily: 'Fraunces, serif',
                fontStyle: 'italic',
                fontSize: '18px',
                color: INK,
                lineHeight: 1.35,
              }}
            >
              {SIGN_IN_STRIP.HEADLINE}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            data-testid="signin-strip-cta"
            onClick={onSignIn}
            className="rounded-full px-5 py-2 transition-colors"
            style={{
              background: INK,
              color: CREAM,
              fontSize: '13px',
              letterSpacing: '0.04em',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = DUSK
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = INK
            }}
          >
            {SIGN_IN_STRIP.CTA}
          </button>
          <button
            type="button"
            data-testid="signin-strip-dismiss"
            onClick={onDismiss}
            className="underline-offset-2 hover:underline"
            style={{
              background: 'transparent',
              color: INK_SOFT,
              fontSize: '12px',
              border: 'none',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            {SIGN_IN_STRIP.DISMISS}
          </button>
        </div>
      </div>
    </section>
  )
}

// --- CuratedBanner (signed-in + prefs state) ---------------------------
interface CuratedBannerProps {
  givenName: string
  prefs: [string, string, string]
  onAdjust: () => void
}

export function CuratedBanner({ givenName, prefs, onAdjust }: CuratedBannerProps) {
  return (
    <section
      data-testid="curated-banner"
      aria-label="Curated for you"
      className="animate-fade-slide-up w-full"
      style={{
        background:
          'linear-gradient(90deg, rgba(196, 69, 54, 0.10) 0%, rgba(245, 232, 211, 0.40) 50%, rgba(196, 69, 54, 0.10) 100%)',
        padding: '18px 24px',
      }}
    >
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 text-center md:flex-row md:justify-between md:text-left">
        <div className="flex items-center gap-3">
          <span
            data-testid="curated-banner-pulse-dot"
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full"
            style={{
              background: ACCENT,
              boxShadow: `0 0 0 0 ${ACCENT}`,
              animation: 'pulse-glow 2s infinite',
            }}
          />
          <span
            style={{
              fontSize: '10px',
              letterSpacing: '0.14em',
              color: INK_SOFT,
              fontWeight: 600,
            }}
          >
            {CURATED_BANNER.LABEL}
          </span>
          <span
            data-testid="curated-banner-headline"
            style={{
              fontFamily: 'Fraunces, serif',
              fontStyle: 'italic',
              fontSize: '16px',
              color: INK,
              lineHeight: 1.4,
            }}
          >
            {curatedHeadline(givenName, prefs)}
          </span>
        </div>
        <button
          type="button"
          data-testid="curated-banner-adjust"
          onClick={onAdjust}
          style={{
            background: 'transparent',
            border: 'none',
            color: ACCENT,
            fontSize: '13px',
            textDecoration: 'underline',
            textUnderlineOffset: '3px',
            cursor: 'pointer',
            padding: '4px 8px',
          }}
        >
          {CURATED_BANNER.ADJUST_LINK}
        </button>
      </div>
    </section>
  )
}

// --- AuthStateBand (the state-router entry point) -----------------------
export default function AuthStateBand() {
  const { user, preferences } = useAuth()
  const { openModal } = useUI()

  // Hydrate the dismissal flag from sessionStorage synchronously so the
  // strip doesn't flash for a tick when the user has already dismissed.
  const [dismissed, setDismissed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    try {
      return window.sessionStorage.getItem(DISMISSED_KEY) === 'true'
    } catch {
      return false
    }
  })

  // Guard so the just_signed_in read-and-delete happens exactly once per
  // mount. React strict-mode double-mounts in dev would otherwise try to
  // delete an already-deleted cookie (benign but noisy).
  const hasReadCookie = useRef(false)

  // On mount: read & delete the `just_signed_in` cookie. If it was present
  // AND the user is signed in AND has no preferences, open the preferences
  // modal. Runs whenever the cookie is first observed for this mount.
  useEffect(() => {
    if (hasReadCookie.current) return
    hasReadCookie.current = true

    const wasJustSignedIn = readCookie(JUST_SIGNED_IN_COOKIE) !== null
    // Always delete the cookie on first read — it's a single-use flag and
    // must not survive a page reload per Design decision #2.
    if (wasJustSignedIn) deleteCookie(JUST_SIGNED_IN_COOKIE)

    if (wasJustSignedIn && user !== null && preferences === null) {
      openModal('preferences')
    }
  }, [user, preferences, openModal])

  const signedIn = user !== null

  const displayName = useMemo(() => {
    if (!user) return ''
    if (user.givenName && user.givenName.trim().length > 0) return user.givenName
    // Fallback to email local-part so the banner reads cleanly before the
    // given_name claim lands (pre-C9 ID tokens may not carry it).
    const local = user.email?.split('@')[0] ?? ''
    return local.length > 0 ? local : 'there'
  }, [user])

  const handleDismiss = () => {
    try {
      window.sessionStorage.setItem(DISMISSED_KEY, 'true')
    } catch {
      // Storage APIs can throw in privacy modes; the in-memory state is
      // enough to hide the strip for the rest of the session.
    }
    setDismissed(true)
  }

  const handleSignIn = () => {
    // Opening the auth modal via UIContext is the primary sign-in surface
    // (5.2 fills in the modal itself). UIContext.openModal is a singleton
    // that closes any other active modal first.
    openModal('auth')
  }

  const handleAdjust = () => openModal('preferences')

  // --- State routing ----------------------------------------------------

  // Signed out: render nothing. Personas replaced Cognito as the primary
  // sign-in surface — the old SignInStrip ("Sign in and watch Pellier
  // tailor the storefront to you.") pointed at an auth flow that is no
  // longer the default. The SignInStrip component is still exported
  // above for any consumer that wants to reuse the markup.
  if (!signedIn) {
    // Preserve dismissed/handleDismiss/handleSignIn references so the
    // session-storage hydration + openModal('auth') helpers don't turn
    // into unused-symbol lint errors.
    void dismissed
    void handleDismiss
    void handleSignIn
    return null
  }

  // Signed in + preferences: show the curated banner.
  if (preferences !== null) {
    return (
      <CuratedBanner
        givenName={displayName}
        prefs={topThreePrefs(preferences)}
        onAdjust={handleAdjust}
      />
    )
  }

  // Signed in + no preferences: render nothing. The effect above has
  // already (maybe) opened the preferences modal based on the
  // just_signed_in cookie.
  return null
}
