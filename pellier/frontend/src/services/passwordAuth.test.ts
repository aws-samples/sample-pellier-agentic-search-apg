import { afterEach, describe, expect, it, vi } from 'vitest'
import { hostedSignInAvailable, passwordAuth, safeSignInReturn } from './passwordAuth'

afterEach(() => vi.unstubAllGlobals())
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
