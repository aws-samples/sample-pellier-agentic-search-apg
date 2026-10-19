import { apiFetch } from './apiBase'
export class PasswordAuthError extends Error {}

type PasswordOperation = 'sign-in' | 'forgot' | 'reset' | 'workshop-sign-in'
export interface PasswordAuthResult {
  status: 'signed_in' | 'verification_required' | 'recovery_requested' | 'password_reset'
  returnTo?: string
  username?: string
  signInMethod?: 'workshop'
}

/** The four shoppers a chip can sign in. Nadia types her password. */
export const WORKSHOP_SHOPPERS = ['anna', 'marco', 'theo', 'jessica'] as const
export type WorkshopShopper = (typeof WORKSHOP_SHOPPERS)[number]

/** The step a failure names: the nonce, then the POST. */
const STEP: Record<PasswordOperation, string> = {
  'sign-in': 'sign_in', 'workshop-sign-in': 'sign_in', forgot: 'forgot', reset: 'reset',
}
const NONCE_RETRY_MS = 500

/**
 * One request, its failure named when Pellier did not answer: `network_error:<step>` when
 * the request never got a reply. An abort stays an abort.
 */
async function send(step: string, path: string, init: RequestInit): Promise<Response> {
  try {
    return await apiFetch(path, init)
  } catch (reason) {
    if (init.signal?.aborted) throw reason
    throw new PasswordAuthError(`network_error:${step}`)
  }
}

/** The reply's JSON, or null when the body is not JSON, such as an edge's own error page. */
async function replyJson<T>(response: Response): Promise<T | null> {
  try {
    return await response.json() as T
  } catch {
    return null
  }
}

function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abandoned = () => {
      clearTimeout(timer)
      reject(new DOMException('The sign-in was abandoned', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abandoned)
      resolve()
    }, ms)
    if (signal.aborted) abandoned()
    else signal.addEventListener('abort', abandoned, { once: true })
  })
}

/**
 * The browser nonce the POST is bound to. Fetching it changes nothing, so a dropped
 * connection gets one retry; an answer that refuses it does not.
 */
async function nonce(signal: AbortSignal): Promise<string> {
  const path = '/api/auth/password/csrf'
  let response: Response
  try {
    response = await send('csrf', path, { credentials: 'include', signal })
  } catch (reason) {
    if (!(reason instanceof PasswordAuthError)) throw reason
    await pause(NONCE_RETRY_MS, signal)
    response = await send('csrf', path, { credentials: 'include', signal })
  }
  if (!response.ok) throw new PasswordAuthError(`http_${response.status}:csrf`)
  const body = await replyJson<{ csrfToken?: string }>(response)
  if (!body?.csrfToken) throw new PasswordAuthError('bad_reply:csrf')
  return body.csrfToken
}

/**
 * Credentials and tokens are never persisted by the browser. No automatic POST retries.
 *
 * A failure carries Pellier's own reason when it gave one (`invalid_credentials`), and
 * otherwise names its cause and step: `network_error:csrf`, `http_403:sign_in`,
 * `bad_reply:csrf`. The page shows a sentence; the code is for the builder.
 */
export async function passwordAuth(
  operation: PasswordOperation,
  body: Record<string, string>,
  signal: AbortSignal,
): Promise<PasswordAuthResult> {
  const csrfToken = await nonce(signal)
  const step = STEP[operation]
  const response = await send(step, `/api/auth/password/${operation}`, {
    method: 'POST', credentials: 'include', signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(body),
  })
  const result = await replyJson<PasswordAuthResult & { detail?: string }>(response)
  if (!response.ok) throw new PasswordAuthError(result?.detail || `http_${response.status}:${step}`)
  if (!result) throw new PasswordAuthError(`bad_reply:${step}`)
  return result
}

/**
 * Whether the edge refused a step before it reached Pellier. The CloudFront firewall answers
 * its rate limit with 429 `requests_limited`; Pellier's own refusals carry other reasons, so
 * a bare 403 or 429 is the firewall too.
 */
export function isRequestsLimited(code: string | null): boolean {
  return code === 'requests_limited' || /^http_(403|429):/.test(code ?? '')
}

/**
 * Sign one provisioned shopper in with one click. A workshop convenience.
 *
 * The browser sends the shopper's username and nothing else; the server reads
 * the provisioned password and performs the same Cognito sign-in a typed
 * password would, so the session is real and signed.
 */
export function workshopSignIn(username: WorkshopShopper, signal: AbortSignal): Promise<PasswordAuthResult> {
  return passwordAuth('workshop-sign-in', { username }, signal)
}

/**
 * Whether this origin can finish a hosted sign-in, so the sign-in page offers
 * one only when it works. An unreachable or unclear answer means no: a
 * missing link is better than one that ends on an error.
 */
export async function hostedSignInAvailable(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await apiFetch('/api/auth/config', { signal })
    if (!response.ok) return false
    const body = await response.json() as { hosted_sign_in?: unknown }
    return body.hosted_sign_in === true
  } catch {
    return false
  }
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
