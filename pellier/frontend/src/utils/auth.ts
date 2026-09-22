import { apiFetch, apiUrl } from '../services/apiBase'
/**
 * utils/auth.ts — auth utility surface.
 *
 * Browser-side helpers for Pellier sign-in and Cognito sessions
 * and a thin re-export of the `useAuth()` React hook from AuthContext.
 *
 * Validates Requirement 2.6.5 and matches the signatures in design.md
 * (Frontend service layer → `utils/auth.ts`). The corresponding backend
 * routes live at `/api/auth/*` (spec tasks 3.3 and 3.4):
 *
 *   redirectToSignIn(provider, opts?)
 *     Email opens Pellier’s dedicated `/signin` page. Federated providers
 *     continue through the server-owned Cognito authorization-code flow.
 *
 *   openSignInChooser(opts?)
 *     Open `/signin?returnTo=<...>`, which mounts <SignInPage/>.
 *     The page offers password entry and a link to configured providers.
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

// === REFERENCE: START ===
import { asset } from './assetPath'
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
 * Open Pellier password sign-in, or start the server-owned authorization-code
 * flow for a federated provider. Both preserve the requested return path.
 */
export function redirectToSignIn(
  provider: SignInProvider,
  opts?: SignInOptions,
): void {
  if (typeof window === 'undefined') return
  const returnTo = resolveReturnTo(opts)
  const url = provider === 'email'
    ? `${asset('/signin')}?returnTo=${encodeURIComponent(returnTo)}`
    : apiUrl(`/api/auth/signin?provider=${encodeURIComponent(provider)}&returnTo=${encodeURIComponent(returnTo)}`)
  window.location.assign(url)
}

/**
 * Open the dedicated sign-in page after a failed silent refresh (Req 4.2.5).
 * It offers password entry and access to configured federated providers.
 */
export function openSignInChooser(opts?: SignInOptions): void {
  if (typeof window === 'undefined') return
  const returnTo = resolveReturnTo(opts)
  const url = `${asset('/signin')}?returnTo=${encodeURIComponent(returnTo)}`
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
    await apiFetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    // Swallow. The client-side redirect below is the user-visible effect.
  }
  window.location.assign(asset('/'))
}

/**
 * `useAuth()` — the single source of truth for the signed-in user,
 * their saved preferences, and the save/refresh helpers. Implemented
 * in `contexts/AuthContext.tsx`; re-exported here so call sites
 * import from one place per the design document.
 */
export const useAuth = useAuthFromContext
// === REFERENCE: END ===
