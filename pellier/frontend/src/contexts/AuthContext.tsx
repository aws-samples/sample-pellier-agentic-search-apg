/**
 * AuthContext — Cognito OAuth2 login + AgentCore Identity-backed preferences.
 *
 * Originally seeded in Lab 4a with the implicit grant (token-in-hash) flow
 * against Cognito Hosted UI. Task 5.1 (Challenge 9.3) extends this context
 * to be the single source of truth for:
 *
 *   - `user`               — Cognito claims (sub, email, givenName)
 *   - `preferences`        — saved preferences from AgentCore Memory
 *   - `refresh()`          — re-reads /api/auth/me + /api/user/preferences
 *   - `savePreferences(p)` — POSTs /api/user/preferences and bumps prefsVersion
 *   - `isLoading`          — alias for `loading` per the design signature
 *   - `prefsVersion`       — monotonic counter ProductGrid uses as `key=`
 *
 * The legacy fields (`login`, `logout`, `accessToken`, `isAuthenticated`,
 * `loading`) remain for backwards compatibility with existing call sites
 * (`LoginButton`, `SignInPage`, `AuthGate`, etc.). New code SHOULD import
 * from `utils/auth.ts` which re-exports `useAuth`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import type { Preferences } from '../services/types'

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

// === LEGACY WIRE IT LIVE (Lab 4a implicit flow) ===
// Kept for the pre-C9 path where there is no backend `/api/auth/*`.
// Participants configure these from CloudFormation outputs; when unset,
// `login()` and `logout()` no-op (the C9 route via `utils/auth.ts` +
// `/api/auth/signin` should be used instead).
const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN || ''
const COGNITO_CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || ''
const REDIRECT_URI = import.meta.env.VITE_COGNITO_REDIRECT_URI || (typeof window !== 'undefined' ? `${window.location.origin}/` : '/')
// === END LEGACY WIRE IT LIVE ===

function parseTokenFromHash(): { accessToken: string; idToken: string } | null {
  if (typeof window === 'undefined') return null
  const hash = window.location.hash.substring(1)
  if (!hash) return null

  const params = new URLSearchParams(hash)
  const accessToken = params.get('access_token')
  const idToken = params.get('id_token')
  if (!accessToken || !idToken) return null

  return { accessToken, idToken }
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const base64 = token.split('.')[1]
    const json = atob(base64.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return {}
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
  const [accessToken, setAccessToken] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('pellier-access-token')
  })
  const [loading, setLoading] = useState(true)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [prefsVersion, setPrefsVersion] = useState(0)

  /**
   * `refresh()` — hydrate `user` from /api/auth/me and `preferences` from
   * /api/user/preferences. Both calls send the httpOnly cookies via
   * `credentials: 'include'`. A 401 on `/api/auth/me` means the user is
   * unauthenticated and we clear any stale state.
   */
  const refresh = useCallback(async () => {
    try {
      const meRes = await fetch('/api/auth/me', {
        method: 'GET',
        credentials: 'include',
      })
      if (!meRes.ok) {
        setUser(null)
        setPreferences(null)
        return
      }
      const me = (await meRes.json()) as MeResponse
      setUser({
        sub: me.userId ?? me.user_id ?? '',
        email: me.email,
        givenName: me.givenName ?? me.given_name,
      })

      // Fetch preferences only once we know we have a verified user.
      const prefsRes = await fetch('/api/user/preferences', {
        method: 'GET',
        credentials: 'include',
      })
      if (prefsRes.ok) {
        const body = (await prefsRes.json()) as PreferencesResponse
        setPreferences(body.preferences ?? null)
      } else {
        setPreferences(null)
      }
    } catch {
      // Network failure — surface as "unauthenticated" rather than leaving
      // stale state. The caller can retry via its own error path.
      setUser(null)
      setPreferences(null)
    }
  }, [])

  /**
   * `savePreferences(p)` — POST /api/user/preferences. On 2xx, bumps
   * `prefsVersion` so the ProductGrid remounts (Req 1.6.6). On non-2xx,
   * throws so the PreferencesModal (Task 5.3) can surface the error.
   */
  const savePreferences = useCallback(async (p: Preferences) => {
    const res = await fetch('/api/user/preferences', {
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
    setPreferences(saved)
    setPrefsVersion(v => v + 1)
  }, [])

  // On mount: the legacy hash flow populates `accessToken` directly from
  // the Cognito Hosted UI redirect; the new C9 flow populates state via
  // `/api/auth/me`. Run both so the component works in either mode.
  useEffect(() => {
    let cancelled = false

    const hydrate = async () => {
      // Legacy implicit-grant path.
      const tokens = parseTokenFromHash()
      if (tokens) {
        localStorage.setItem('pellier-access-token', tokens.accessToken)
        localStorage.setItem('pellier-id-token', tokens.idToken)
        if (!cancelled) setAccessToken(tokens.accessToken)

        const claims = decodeJwtPayload(tokens.idToken)
        if (!cancelled) {
          setUser({
            sub: (claims.sub as string) || '',
            email: (claims.email as string) || 'user',
            givenName: (claims.given_name as string) || undefined,
          })
        }
        // Clean up URL hash so a refresh doesn't re-parse old tokens.
        if (typeof window !== 'undefined') {
          window.history.replaceState(
            null,
            '',
            window.location.pathname + window.location.search,
          )
        }
      } else if (accessToken) {
        const idToken =
          typeof window !== 'undefined'
            ? localStorage.getItem('pellier-id-token')
            : null
        if (idToken) {
          const claims = decodeJwtPayload(idToken)
          const exp = claims.exp as number | undefined
          if (exp && exp * 1000 > Date.now()) {
            if (!cancelled) {
              setUser({
                sub: (claims.sub as string) || '',
                email: (claims.email as string) || 'user',
                givenName: (claims.given_name as string) || undefined,
              })
            }
          } else if (typeof window !== 'undefined') {
            localStorage.removeItem('pellier-access-token')
            localStorage.removeItem('pellier-id-token')
            if (!cancelled) setAccessToken(null)
          }
        }
      }

      // Cookie-backed /api/auth/me path — only fire when we have
      // evidence of an active Cognito session (legacy token present
      // or an auth callback just ran). Firing on every cold mount
      // produces a noisy 401 for every storefront visit, which is
      // the common case now that personas replaced Cognito as the
      // primary sign-in mechanism. When Cognito IS wired, the hash
      // path above populates user/accessToken and we still want to
      // cross-check server claims.
      if (tokens || accessToken) {
        await refresh()
      }

      if (!cancelled) setLoading(false)
    }

    void hydrate()
    return () => {
      cancelled = true
    }
    // Intentional: refresh is stable (useCallback with empty deps) and
    // accessToken is only read on first mount.
  }, [])

  const login = useCallback(() => {
    if (!COGNITO_DOMAIN || !COGNITO_CLIENT_ID) {
      console.warn(
        'Cognito not configured — set VITE_COGNITO_DOMAIN and VITE_COGNITO_CLIENT_ID',
      )
      return
    }
    const authUrl =
      `https://${COGNITO_DOMAIN}/login?` +
      `client_id=${COGNITO_CLIENT_ID}` +
      `&response_type=token` +
      `&scope=openid+email+profile` +
      `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}`
    window.location.href = authUrl
  }, [])

  const logout = useCallback(() => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('pellier-access-token')
      localStorage.removeItem('pellier-id-token')
    }
    setUser(null)
    setAccessToken(null)
    setPreferences(null)

    if (COGNITO_DOMAIN && COGNITO_CLIENT_ID) {
      const logoutUrl =
        `https://${COGNITO_DOMAIN}/logout?` +
        `client_id=${COGNITO_CLIENT_ID}` +
        `&logout_uri=${encodeURIComponent(REDIRECT_URI)}`
      window.location.href = logoutUrl
    }
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
