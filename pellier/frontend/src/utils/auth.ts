/**
 * utils/auth.ts — Challenge 9.3 surface.
 *
 * Browser-side helpers for the Cognito Hosted UI + AgentCore Identity flow
 * and a thin re-export of the `useAuth()` React hook from AuthContext.
 *
 * Validates Requirement 2.6.5 and matches the signatures in design.md
 * (Frontend service layer → `utils/auth.ts`). The corresponding backend
 * routes live at `/api/auth/*` (spec tasks 3.3 and 3.4):
 *
 *   redirectToSignIn(provider, opts?)
 *     Full-page navigate to `/api/auth/signin?provider=<p>&returnTo=<...>`.
 *     The server 302s onward to Cognito Hosted UI with the right IdP hint.
 *
 *   openSignInChooser(opts?)
 *     SPA-route to `/signin?returnTo=<...>`, which mounts <AuthModal/>
 *     (Task 5.2). ALL three provider buttons are visible so a user who
 *     originally signed in with Google is not silently forced into
 *     email/password during a re-auth.
 *
 *   redirectToLogout()
 *     POST /api/auth/logout (server clears httpOnly cookies and revokes
 *     the refresh token against Cognito), then navigate to `/`.
 *
 *   useAuth()
 *     Re-export of the hook from `contexts/AuthContext.tsx` so the
 *     utils/auth module is the one canonical import surface per the
 *     design document.
 *
 * The `services/api.ts` 401 interceptor also lives inside the same
 * challenge feature — it calls `/api/auth/refresh` on 401, retries the
 * original request once on success, and falls through to
 * `openSignInChooser({ returnTo: ... })` when refresh fails.
 */

// === CHALLENGE 9.3: START ===
import { useAuth as useAuthFromContext } from '../contexts/AuthContext'

export type SignInProvider = 'google' | 'apple' | 'email'

export interface SignInOptions {
  /**
   * Path + search the user should land on after the sign-in round trip.
   * Defaults to the current pathname + search when not provided. Never
   * includes the hash (Cognito strips it on the redirect chain anyway).
   */
  returnTo?: string
}

/** Build `?returnTo=<encoded>` from the current URL when no override is passed. */
function resolveReturnTo(opts?: SignInOptions): string {
  if (opts?.returnTo !== undefined && opts.returnTo !== null) return opts.returnTo
  if (typeof window === 'undefined') return '/'
  const { pathname, search } = window.location
  return `${pathname}${search}`
}

/**
 * `redirectToSignIn` — kick the full-page OAuth2 code flow for a specific
 * IdP. The server handles state generation, CSRF, PKCE (if configured),
 * and the Cognito 302.
 */
export function redirectToSignIn(
  provider: SignInProvider,
  opts?: SignInOptions,
): void {
  if (typeof window === 'undefined') return
  const returnTo = resolveReturnTo(opts)
  const url =
    `/api/auth/signin?provider=${encodeURIComponent(provider)}` +
    `&returnTo=${encodeURIComponent(returnTo)}`
  window.location.assign(url)
}

/**
 * `openSignInChooser` — SPA-route to `/signin?returnTo=...`. The
 * `/signin` route mounts `<AuthModal/>` (Task 5.2) over the previous page
 * and shows all three providers without preselection.
 *
 * This is the safe fallback after a failed silent refresh (Req 4.2.5).
 * We deliberately do NOT pick a provider here — the user does, preserving
 * whichever IdP they originally chose.
 */
export function openSignInChooser(opts?: SignInOptions): void {
  if (typeof window === 'undefined') return
  const returnTo = resolveReturnTo(opts)
  const url = `/signin?returnTo=${encodeURIComponent(returnTo)}`
  window.location.assign(url)
}

/**
 * `redirectToLogout` — POST /api/auth/logout so the server can clear the
 * three httpOnly cookies and revoke the refresh token, then navigate
 * home. Failures are swallowed — logout must never leave the user
 * appearing signed in on the client.
 */
export async function redirectToLogout(): Promise<void> {
  if (typeof window === 'undefined') return
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    // Swallow. The client-side redirect below is the user-visible effect.
  }
  window.location.assign('/')
}

/**
 * `useAuth()` — the single source of truth for the signed-in user,
 * their saved preferences, and the save/refresh helpers. Implemented
 * in `contexts/AuthContext.tsx`; re-exported here so call sites
 * import from one place per the design document.
 */
export const useAuth = useAuthFromContext
// === CHALLENGE 9.3: END ===
