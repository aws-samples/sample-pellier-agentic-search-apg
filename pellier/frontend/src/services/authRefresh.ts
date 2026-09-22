import { apiFetch } from './apiBase'
/**
 * Shared in-flight refresh promise. When multiple requests 401
 * simultaneously they all await the same /api/auth/refresh call rather
 * than triggering a thundering herd.
 */
let refreshInFlight: Promise<boolean> | null = null
export const AUTH_REFRESH_TIMEOUT_MS = 12_000

/**
 * Call /api/auth/refresh with the current cookies. Returns true when the
 * server responds 2xx (new cookies set server-side), false only for 401.
 * An unavailable provider throws; it has not rejected the session.
 * Exported only for tests.
 */
export async function refreshAuthTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  const request = (async () => {
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(() => controller.abort(), AUTH_REFRESH_TIMEOUT_MS)
    try {
      const res = await apiFetch('/api/auth/refresh', {
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
  refreshInFlight = request.finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}
