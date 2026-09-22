import { apiFetch } from './apiBase'
export class PasswordAuthError extends Error {}

type PasswordOperation = 'sign-in' | 'forgot' | 'reset'
export interface PasswordAuthResult {
  status: 'signed_in' | 'verification_required' | 'recovery_requested' | 'password_reset'
  returnTo?: string
}

/** Credentials and tokens are never persisted by the browser. No automatic POST retries. */
export async function passwordAuth(
  operation: PasswordOperation,
  body: Record<string, string>,
  signal: AbortSignal,
): Promise<PasswordAuthResult> {
  const csrf = await apiFetch('/api/auth/password/csrf', { credentials: 'include', signal })
  if (!csrf.ok) throw new PasswordAuthError('auth_unavailable')
  const { csrfToken } = await csrf.json() as { csrfToken: string }
  if (!csrfToken) throw new PasswordAuthError('auth_unavailable')
  const response = await apiFetch(`/api/auth/password/${operation}`, {
    method: 'POST', credentials: 'include', signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(body),
  })
  const result = await response.json() as PasswordAuthResult & { detail?: string }
  if (!response.ok) throw new PasswordAuthError(result.detail || 'auth_unavailable')
  return result
}

/** Same-origin navigation, including deployments with a router base path. */
export function safeSignInReturn(value: string | null, fallback = '/'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || (value.includes('\\') || [...value].some((character) => character.charCodeAt(0) < 32))) return fallback
  try {
    const url = new URL(value, window.location.origin)
    if (url.origin !== window.location.origin || /\/signin\/?$/.test(url.pathname)) return fallback
    return `${url.pathname}${url.search}${url.hash}`
  } catch { return fallback }
}
