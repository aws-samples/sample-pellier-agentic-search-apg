import { afterEach, describe, expect, it, vi } from 'vitest'
import { hostedSignInAvailable, isRequestsLimited, passwordAuth, safeSignInReturn } from './passwordAuth'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
describe('password authentication transport', () => {
  it('binds the POST to a browser nonce and never retries it', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'signed-nonce' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'invalid_credentials' }), { status: 401 }))
    vi.stubGlobal('fetch', fetch)
    await expect(passwordAuth('sign-in', { username: 'operator', password: 'private' }, new AbortController().signal)).rejects.toThrow('invalid_credentials')
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1][1]).toMatchObject({ credentials: 'include', method: 'POST', headers: { 'X-CSRF-Token': 'signed-nonce' } })
  })
  it.each(['https://other.example', '//other.example', '/\\other.example', '/signin?returnTo=/signin'])('refuses unsafe or recursive destination %s', (value) => {
    expect(safeSignInReturn(value)).toBe('/')
  })
})
describe('a sign-in step that fails before Pellier answers', () => {
  const nonce = () => Promise.resolve(new Response(JSON.stringify({ csrfToken: 'signed-nonce' })))
  const signedIn = () => Promise.resolve(new Response(JSON.stringify({ status: 'signed_in' })))
  const edgePage = (status: number) => () => Promise.resolve(new Response('<html>Request blocked.</html>', { status }))
  const dropped = () => Promise.reject(new TypeError('Failed to fetch'))
  const signIn = () => passwordAuth('workshop-sign-in', { username: 'marco' }, new AbortController().signal)

  it('retries the nonce once after a dropped connection, then signs in', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn().mockImplementationOnce(dropped).mockImplementationOnce(nonce).mockImplementationOnce(signedIn)
    vi.stubGlobal('fetch', fetch)
    const result = signIn()
    await vi.advanceTimersByTimeAsync(499)
    expect(fetch).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await expect(result).resolves.toMatchObject({ status: 'signed_in' })
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(fetch.mock.calls[2][1]).toMatchObject({ method: 'POST' })
  })
  it('names the nonce step when the connection drops twice, and sends no POST', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(dropped)
    vi.stubGlobal('fetch', fetch)
    const result = expect(signIn()).rejects.toThrow('network_error:csrf')
    await vi.advanceTimersByTimeAsync(500)
    await result
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it.each([[403], [429], [502]])('names an edge reply %i to the nonce without retrying it', async (status) => {
    const fetch = vi.fn(edgePage(status))
    vi.stubGlobal('fetch', fetch)
    await expect(signIn()).rejects.toThrow(`http_${status}:csrf`)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('names a nonce reply that carries no nonce', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}'))))
    await expect(signIn()).rejects.toThrow('bad_reply:csrf')
  })
  it('never retries the POST: a dropped sign-in is named and sent once', async () => {
    const fetch = vi.fn().mockImplementationOnce(nonce).mockImplementation(dropped)
    vi.stubGlobal('fetch', fetch)
    await expect(signIn()).rejects.toThrow('network_error:sign_in')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it("names an edge refusal of the POST, and keeps Pellier's own reason when it gives one", async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementationOnce(nonce).mockImplementationOnce(edgePage(403)))
    await expect(signIn()).rejects.toThrow('http_403:sign_in')
    vi.stubGlobal('fetch', vi.fn().mockImplementationOnce(nonce).mockImplementationOnce(
      () => Promise.resolve(new Response(JSON.stringify({ detail: 'workshop_user_not_allowed' }), { status: 403 }))))
    await expect(signIn()).rejects.toThrow('workshop_user_not_allowed')
  })
  it('stops waiting to retry when the choice is abandoned', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(dropped)
    vi.stubGlobal('fetch', fetch)
    const abort = new AbortController()
    const result = expect(passwordAuth('workshop-sign-in', { username: 'marco' }, abort.signal)).rejects.toMatchObject({ name: 'AbortError' })
    await vi.advanceTimersByTimeAsync(100)
    abort.abort()
    await result
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it("reads the firewall's 429 reply on the POST as requests being limited", async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementationOnce(nonce).mockImplementationOnce(
      () => Promise.resolve(new Response(JSON.stringify({ detail: 'requests_limited' }), { status: 429 }))))
    const failure = await signIn().then(() => '', (reason: Error) => reason.message)
    expect(isRequestsLimited(failure)).toBe(true)
  })
  it('reads only an edge refusal as requests being limited', () => {
    expect(isRequestsLimited('http_403:csrf')).toBe(true)
    expect(isRequestsLimited('http_429:sign_in')).toBe(true)
    expect(isRequestsLimited('requests_limited')).toBe(true)
    for (const code of ['http_502:csrf', 'network_error:csrf', 'workshop_user_not_allowed', 'auth_unavailable', null]) {
      expect(isRequestsLimited(code)).toBe(false)
    }
  })
})
describe('hosted sign-in availability', () => {
  it('asks the server and believes only an explicit yes', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ hosted_sign_in: true })))
    vi.stubGlobal('fetch', fetch)
    await expect(hostedSignInAvailable()).resolves.toBe(true)
    expect(fetch.mock.calls[0][0]).toBe('/api/auth/config')
  })
  it.each([
    ['a no', () => Promise.resolve(new Response(JSON.stringify({ hosted_sign_in: false })))],
    ['an unclear answer', () => Promise.resolve(new Response(JSON.stringify({ hosted_sign_in: 'yes' })))],
    ['an error status', () => Promise.resolve(new Response('{}', { status: 503 }))],
    ['no answer', () => Promise.reject(new TypeError('network'))],
  ])('reads %s as not available', async (_label, reply) => {
    vi.stubGlobal('fetch', vi.fn(reply))
    await expect(hostedSignInAvailable()).resolves.toBe(false)
  })
})
