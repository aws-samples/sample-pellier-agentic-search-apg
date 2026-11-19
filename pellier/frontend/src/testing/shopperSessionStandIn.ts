/**
 * A browser-shaped stand-in for the shopper sign-in routes, for unit tests that run the
 * real `AuthProvider` and `PersonaProvider`.
 *
 * It models the one thing that makes sign-in order matter: a cookie jar. A workshop
 * sign-in changes the jar's shopper only when the browser would apply its response, which
 * is never for a request aborted before the response arrived. `/api/auth/me` answers from
 * the jar. Sign-ins wait until the test releases them, so a test decides which response
 * arrives first.
 */
import { waitFor } from '@testing-library/react'
import { expect, vi } from 'vitest'

export interface HeldSignIn {
  shopper: string
  signal: AbortSignal
  /** The response arrives: the jar changes unless the request was already aborted. */
  release: () => void
  /** The server answers with a refusal. */
  refuse: () => void
}

export interface ShopperSessionStandIn {
  /** The shopper the browser's session cookie belongs to. */
  jar: { shopper: string | null }
  /** Every workshop sign-in request, in the order the browser sent it. */
  signIns: HeldSignIn[]
  /** Paths of every request, for tests that count them. */
  requests: string[]
  /** What `/api/auth/me` will say instead of the jar, to model a session that disagrees. */
  meSays: { shopper: string | null | undefined }
  /** Wait for the nth sign-in to be sent. */
  nth: (index: number) => Promise<HeldSignIn>
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function personaFor(id: string) {
  const name = id.charAt(0).toUpperCase() + id.slice(1)
  return {
    id, edit: id, display_name: name, role_tag: `${name}'s edit`, avatar_color: '#333',
    avatar_initial: name[0], customer_id: `CUST-${id.toUpperCase()}`, hero_image: '', hero_alt: name,
    hero_subheadline: '', stats: { visits: 1, orders: 1, last_seen_days: 1 },
  }
}

function abortError(): DOMException {
  return new DOMException('The request was aborted', 'AbortError')
}

function holdSignIn(shopper: string, signal: AbortSignal, held: HeldSignIn[], jar: { shopper: string | null }) {
  return new Promise<Response>((resolve, reject) => {
    let settled = false
    const settle = (finish: () => void) => {
      if (settled) return
      settled = true
      finish()
    }
    signal.addEventListener('abort', () => settle(() => reject(abortError())), { once: true })
    held.push({
      shopper,
      signal,
      release: () => settle(() => {
        jar.shopper = shopper
        resolve(json({ status: 'signed_in', username: shopper, signInMethod: 'workshop' }))
      }),
      refuse: () => settle(() => resolve(json({ detail: 'workshop_sign_in_unavailable' }, 503))),
    })
  })
}

export function installShopperSessionStandIn(): ShopperSessionStandIn {
  const jar = { shopper: null as string | null }
  const signIns: HeldSignIn[] = []
  const requests: string[] = []
  const meSays: ShopperSessionStandIn['meSays'] = { shopper: undefined }

  const answer = (path: string, init: RequestInit | undefined): Promise<Response> => {
    if (path.startsWith('/api/auth/password/csrf')) return Promise.resolve(json({ csrfToken: 'csrf' }))
    if (path.startsWith('/api/auth/password/workshop-sign-in')) {
      const { username } = JSON.parse(String(init?.body)) as { username: string }
      if (init?.signal?.aborted) return Promise.reject(abortError())
      return holdSignIn(username, init?.signal ?? new AbortController().signal, signIns, jar)
    }
    if (path.startsWith('/api/auth/me')) {
      const shopper = meSays.shopper === undefined ? jar.shopper : meSays.shopper
      return Promise.resolve(shopper
        ? json({ user_id: `sub-${shopper}`, email: `${shopper}@pellier.example.com`, username: shopper })
        : json({ error: 'auth_failed' }, 401))
    }
    if (path.startsWith('/api/auth/')) return Promise.resolve(json({ error: 'refresh_failed' }, 401))
    if (path.startsWith('/api/user/preferences')) return Promise.resolve(json({ preferences: null }))
    if (path.startsWith('/api/persona/switch')) {
      const { persona_id: id } = JSON.parse(String(init?.body)) as { persona_id: string }
      return Promise.resolve(json({ session_id: `persona-${id}-${requests.length}`, persona: personaFor(id) }))
    }
    return Promise.resolve(json({}))
  }

  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    requests.push(String(url))
    return answer(String(url), init)
  }))

  const nth = async (index: number): Promise<HeldSignIn> => {
    await waitFor(() => expect(signIns.length).toBeGreaterThan(index))
    return signIns[index]
  }
  return { jar, signIns, requests, meSays, nth }
}
