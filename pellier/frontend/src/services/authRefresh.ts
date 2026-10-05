import { apiFetch } from './apiBase'

/**
 * The two sessions one browser holds: the shopper's on the storefront and
 * the staff member's on the Operator. Each has its own httpOnly cookies, and
 * every `/api/auth` call names the one it means.
 */
export type AuthSurface = 'shopper' | 'staff'

/**
 * One in-flight refresh per surface. When multiple requests 401
 * simultaneously they all await the same /api/auth/refresh call rather
 * than triggering a thundering herd, and a staff refresh never waits on,
 * or stands in for, a shopper one.
 */
const refreshInFlight = new Map<AuthSurface, Promise<boolean>>()
export const AUTH_REFRESH_TIMEOUT_MS = 12_000

/**
 * Call /api/auth/refresh for one surface's session. Returns true when the
 * server responds 2xx (new cookies set server-side), false only for 401.
 * An unavailable provider throws; it has not rejected the session.
 */
export async function refreshAuthTokens(surface: AuthSurface = 'shopper'): Promise<boolean> {
  const pending = refreshInFlight.get(surface)
  if (pending) return pending
  const request = (async () => {
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(() => controller.abort(), AUTH_REFRESH_TIMEOUT_MS)
    try {
      const res = await apiFetch(`/api/auth/refresh?surface=${surface}`, {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
      })
      if (res.ok) return true
      if (res.status === 401) return false
      throw new Error('auth_unavailable')
    } finally {
      globalThis.clearTimeout(timeout)
    }
  })()
  const shared = request.finally(() => {
    refreshInFlight.delete(surface)
  })
  refreshInFlight.set(surface, shared)
  return shared
}
