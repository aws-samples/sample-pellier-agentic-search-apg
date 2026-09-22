import { apiFetch } from '../services/apiBase'
/**
 * AuthContext — Cognito OAuth2 login + AgentCore Identity-backed preferences.
 *
 * Uses the backend authorization-code flow. Cognito tokens remain in secure,
 * httpOnly cookies set by `/api/auth/callback`; browser code never handles
 * tokens from a URL fragment or localStorage. This context is the source of
 * truth for:
 *
 *   - `user`               — Cognito claims (sub, email, givenName)
 *   - `preferences`        — saved preferences from AgentCore Memory
 *   - `refresh()`          — re-reads /api/auth/me + /api/user/preferences
 *   - `savePreferences(p)` — POSTs /api/user/preferences and bumps prefsVersion
 *   - `isLoading`          — alias for `loading` per the design signature
 *   - `prefsVersion`       — monotonic counter ProductGrid uses as `key=`
 *
 * The fields (`login`, `logout`, `accessToken`, `isAuthenticated`, `loading`)
 * remain compatible with existing call sites
 * (`LoginButton`, `SignInPage`, `OperatorFrame`, etc.). New code SHOULD
 * import from `utils/auth.ts` which re-exports `useAuth`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { asset } from '../utils/assetPath'
import type { Preferences } from '../services/types'
import { refreshAuthTokens } from '../services/authRefresh'

interface AuthUser {
  sub: string
  email: string
  givenName?: string
}

interface AuthContextType {
  user: AuthUser | null
  isAuthenticated: boolean
  accessToken: string | null
  login: () => void
  logout: () => void
  loading: boolean
  /** Alias for `loading` — matches the design-document signature. */
  isLoading: boolean
  /** A failed verification is distinct from rejected or absent credentials. */
  authUnavailable: boolean
  preferencesUnavailable: boolean
  /**
   * Saved preferences from AgentCore Memory, fetched via
   * `/api/user/preferences`. `null` means either unauthenticated or no
   * preferences saved yet. AuthStateBand (Task 4.4) uses the null branch
   * to trigger the preferences onboarding modal.
   */
  preferences: Preferences | null
  /**
   * Monotonic counter that advances each time preferences are saved.
   * `ProductGrid` (Task 4.6) uses this as `key={prefsVersion}` so the
   * grid remounts and re-fires the parallax reveal on every save
   * (Req 1.6.6). Starts at 0.
   */
  prefsVersion: number
  /**
   * Re-read /api/auth/me and /api/user/preferences. Called by the app
   * shell after a sign-in callback and on first mount.
   */
  refresh: () => Promise<void>
  /**
   * POST /api/user/preferences. On success, updates local state and
   * advances `prefsVersion` so the product grid remounts and re-parallaxes.
   */
  savePreferences: (p: Preferences) => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/**
 * Auth state for components that also mount without the provider (unit
 * tests, isolated portals). Returns null instead of throwing so callers can
 * treat "no provider" as "not authenticated".
 */
export function useOptionalAuth(): AuthContextType | null {
  return useContext(AuthContext) ?? null
}

const AUTH_SESSION_MARKER_KEY = 'pellier-auth-session'
/** A hung local proxy must not strand every surface in its auth loading state. */
export const AUTH_REQUEST_TIMEOUT_MS = 8_000

async function authFetch(path: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(
    () => controller.abort(),
    AUTH_REQUEST_TIMEOUT_MS,
  )

  try {
    return await apiFetch(path, { ...init, signal: controller.signal })
  } finally {
    globalThis.clearTimeout(timeout)
  }
}

// Shape returned by GET /api/auth/me (see Req 3.1.3). The server returns
// camelCase fields matching the `User` wire type in services/types.ts.
interface MeResponse {
  userId?: string
  user_id?: string
  email: string
  givenName?: string
  given_name?: string
}

// Shape returned by GET /api/user/preferences (see Req 3.2.1). The server
// returns `{ preferences: Preferences | null }`; we only care about the
// inner object.
interface PreferencesResponse {
  preferences: Preferences | null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const accessToken: string | null = null
  const [loading, setLoading] = useState(true)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [prefsVersion, setPrefsVersion] = useState(0)
  const [authUnavailable, setAuthUnavailable] = useState(false)
  const [preferencesUnavailable, setPreferencesUnavailable] = useState(false)
  const refreshGeneration = useRef(0)
  const verifiedSubject = useRef<string | null>(null)
  const identityGeneration = useRef(0)

  /**
   * `refresh()` — hydrate `user` from /api/auth/me and `preferences` from
   * /api/user/preferences. Both calls send the httpOnly cookies via
   * `credentials: 'include'`. A 401 on `/api/auth/me` means the user is
   * unauthenticated and we clear any stale state.
   */
  const refresh = useCallback(async () => {
    const generation = ++refreshGeneration.current
    const isCurrent = () => generation === refreshGeneration.current
    try {
      let meRes = await authFetch('/api/auth/me', {
        method: 'GET',
        credentials: 'include',
      })
      if (!isCurrent()) return
      if (meRes.status === 401 && await refreshAuthTokens()) {
        meRes = await authFetch('/api/auth/me', {
          method: 'GET',
          credentials: 'include',
        })
      }
      if (!isCurrent()) return
      if (meRes.status === 401) {
        verifiedSubject.current = null
        ++identityGeneration.current
        setAuthUnavailable(false)
        setPreferencesUnavailable(false)
        setUser(null)
        setPreferences(null)
        if (typeof window !== 'undefined') {
          const hadSession = localStorage.getItem(AUTH_SESSION_MARKER_KEY) === '1'
          localStorage.removeItem(AUTH_SESSION_MARKER_KEY)
          if (hadSession && !/\/signin\/?$/.test(window.location.pathname)) {
            const returnTo = window.location.pathname + window.location.search
            window.location.assign(`${asset('/signin')}?returnTo=${encodeURIComponent(returnTo)}`)
          }
        }
        return
      }
      if (!meRes.ok) {
        setAuthUnavailable(true)
        return
      }
      const me = (await meRes.json()) as MeResponse
      if (!isCurrent()) return
      const subject = me.userId ?? me.user_id
      if (!subject) {
        setAuthUnavailable(true)
        return
      }
      if (verifiedSubject.current !== subject) {
        verifiedSubject.current = subject
        ++identityGeneration.current
        // A different cookie identity must never inherit the previous person's
        // preferences, including while its own request is pending or unavailable.
        setPreferences(null)
        setPreferencesUnavailable(true)
      }
      setAuthUnavailable(false)
      if (typeof window !== 'undefined') {
        localStorage.setItem(AUTH_SESSION_MARKER_KEY, '1')
      }
      setUser({
        sub: subject,
        email: me.email,
        givenName: me.givenName ?? me.given_name,
      })

      // Fetch preferences only once we know we have a verified user.
      try {
        const prefsRes = await authFetch('/api/user/preferences', {
          method: 'GET',
          credentials: 'include',
        })
        if (!isCurrent()) return
        if (!prefsRes.ok) {
          setPreferencesUnavailable(true)
          return
        }
        const body = (await prefsRes.json()) as PreferencesResponse
        if (!isCurrent()) return
        setPreferences(body.preferences ?? null)
        setPreferencesUnavailable(false)
      } catch {
        if (isCurrent()) setPreferencesUnavailable(true)
      }
    } catch {
      // Keep the last verified profile while displaying the outage. Every
      // protected API still verifies the cookie; this grants no authority.
      if (isCurrent()) setAuthUnavailable(true)
    }
  }, [])

  /**
   * `savePreferences(p)` — POST /api/user/preferences. On 2xx, bumps
   * `prefsVersion` so the ProductGrid remounts (Req 1.6.6). On non-2xx,
   * throws so the PreferencesModal (Task 5.3) can surface the error.
   */
  const savePreferences = useCallback(async (p: Preferences) => {
    const generation = identityGeneration.current
    const res = await authFetch('/api/user/preferences', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(p),
    })
    if (!res.ok) {
      throw new Error(`savePreferences failed: HTTP ${res.status}`)
    }
    // Server echoes the saved object (Req 3.2.2). Prefer the echo over the
    // input so any server-side normalization is respected.
    let saved: Preferences = p
    try {
      const body = await res.json()
      if (body && typeof body === 'object') {
        // Accept either `{ preferences: Preferences }` or a bare Preferences.
        saved = (body.preferences ?? body) as Preferences
      }
    } catch {
      // Empty body is fine — keep the input.
    }
    if (generation !== identityGeneration.current || !verifiedSubject.current) return
    setPreferences(saved)
    setPrefsVersion(v => v + 1)
  }, [])

  // The session cookies are httpOnly by design, so JavaScript cannot reliably
  // predict whether they exist. Always ask the server once on mount. A clean
  // anonymous load checks both access and refresh cookies; skipping this can strand a
  // valid operator session in a signed-out SPA state.
  useEffect(() => {
    let cancelled = false

    const hydrate = async () => {
      await refresh()
      if (!cancelled) setLoading(false)
    }

    void hydrate()
    return () => {
      cancelled = true
    }
  }, [refresh])

  const login = useCallback(() => {
    const returnTo = `${window.location.pathname}${window.location.search}`
    window.location.assign(
      `${asset('/signin')}?returnTo=${encodeURIComponent(returnTo)}`,
    )
  }, [])

  const logout = useCallback(() => {
    ++refreshGeneration.current
    verifiedSubject.current = null
    ++identityGeneration.current
    setAuthUnavailable(false)
    setPreferencesUnavailable(false)
    localStorage.removeItem(AUTH_SESSION_MARKER_KEY)
    setUser(null)
    setPreferences(null)
    void authFetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    }).finally(() => window.location.reload())
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        accessToken,
        login,
        logout,
        loading,
        isLoading: loading,
        authUnavailable,
        preferencesUnavailable,
        preferences,
        prefsVersion,
        refresh,
        savePreferences,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
