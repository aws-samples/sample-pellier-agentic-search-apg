/**
 * Every shopper sign-in in the browser answers to one coordinator.
 *
 * Runs the real `AuthProvider` and `PersonaProvider` against a stand-in that models the
 * browser's session cookie, so what is asserted is where the session ends up: the shopper
 * on screen, the shopper `/api/auth/me` reports, and nothing more.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import { PersonaProvider, usePersona } from '../contexts/PersonaContext'
import { installShopperSessionStandIn, type ShopperSessionStandIn } from '../testing/shopperSessionStandIn'
import { useShopperSessionRefresh, useShopperSignIn } from './useShopperSignIn'

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider surface="shopper"><PersonaProvider>{children}</PersonaProvider></AuthProvider>
)

/** Two chooser instances (the panel's and the header's), the session refresh and both contexts. */
function mountBrowser() {
  return renderHook(() => ({
    panel: useShopperSignIn(),
    header: useShopperSignIn(),
    refreshSession: useShopperSessionRefresh(),
    persona: usePersona(),
    auth: useAuth(),
  }), { wrapper })
}

let browser: ShopperSessionStandIn

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  browser = installShopperSessionStandIn()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function meSays(): Promise<string | undefined> {
  const response = await fetch('/api/auth/me?surface=shopper')
  return response.ok ? ((await response.json()) as { username: string }).username : undefined
}

describe('two choosers racing', () => {
  it('leaves the session, the persona and the verified user with the latest choice', async () => {
    const { result } = mountBrowser()
    let first: Promise<boolean> = Promise.resolve(false)
    let second: Promise<boolean> = Promise.resolve(false)
    act(() => { first = result.current.panel.choose('theo') })
    const theo = await browser.nth(0)
    act(() => { second = result.current.header.choose('anna') })
    const anna = await browser.nth(1)
    await act(async () => {
      anna.release()
      expect(await second).toBe(true)
      // Theo's response arrives after Anna has been chosen and signed in.
      theo.release()
      expect(await first).toBe(false)
    })
    expect(browser.jar.shopper).toBe('anna')
    expect(await meSays()).toBe('anna')
    expect(result.current.persona.persona?.id).toBe('anna')
    expect(result.current.auth.user?.username).toBe('anna')
    expect(result.current.persona.switching).toBe(false)
    expect(result.current.panel.busy).toBeNull()
    expect(result.current.panel.error).toBeNull()
  })

  it('keeps the earlier shopper from applying even when its response came first', async () => {
    const { result } = mountBrowser()
    let first: Promise<boolean> = Promise.resolve(false)
    let second: Promise<boolean> = Promise.resolve(false)
    act(() => { first = result.current.panel.choose('theo') })
    const theo = await browser.nth(0)
    await act(async () => { theo.release() })
    act(() => { second = result.current.header.choose('marco') })
    const marco = await browser.nth(1)
    await act(async () => {
      marco.release()
      await Promise.all([first, second])
    })
    expect(browser.jar.shopper).toBe('marco')
    expect(result.current.persona.persona?.id).toBe('marco')
    expect(result.current.auth.user?.username).toBe('marco')
  })

  it('does not name a shopper the server session does not belong to', async () => {
    const { result } = mountBrowser()
    browser.meSays.shopper = 'jessica'
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    let chosen: Promise<boolean> = Promise.resolve(true)
    act(() => { chosen = result.current.panel.choose('theo') })
    await act(async () => {
      ;(await browser.nth(0)).release()
      expect(await chosen).toBe(false)
    })
    expect(result.current.persona.persona).toBeNull()
    await waitFor(() => expect(result.current.panel.error).toBe('session_mismatch'))
    warn.mockRestore()
  })
})

describe('a session that cannot be confirmed', () => {
  it('reports the session as unavailable when /api/auth/me names no one', async () => {
    const { result } = mountBrowser()
    browser.meSays.shopper = null
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    let chosen: Promise<boolean> = Promise.resolve(true)
    act(() => { chosen = result.current.panel.choose('theo') })
    await act(async () => {
      ;(await browser.nth(0)).release()
      expect(await chosen).toBe(false)
    })
    expect(result.current.persona.persona).toBeNull()
    await waitFor(() => expect(result.current.panel.error).toBe('auth_unavailable'))
    warn.mockRestore()
  })
})

describe('signing out while a sign-in is pending', () => {
  it('abandons the sign-in, so its late response cannot sign the shopper back in', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload, assign: vi.fn() })
    const { result } = mountBrowser()
    let chosen: Promise<boolean> = Promise.resolve(true)
    act(() => { chosen = result.current.panel.choose('theo') })
    const theo = await browser.nth(0)
    await act(async () => {
      result.current.panel.signOut()
      theo.release()
      expect(await chosen).toBe(false)
    })
    expect(browser.jar.shopper).toBeNull()
    expect(result.current.persona.persona).toBeNull()
    expect(result.current.persona.switching).toBe(false)
  })
})

describe('the expired-session sign in again shares the coordinator', () => {
  it('is superseded by a shopper chosen while it is pending, and its late response changes nothing', async () => {
    const { result } = mountBrowser()
    let again: Promise<unknown> = Promise.resolve('')
    let chosen: Promise<boolean> = Promise.resolve(false)
    act(() => { again = result.current.refreshSession('theo') })
    const theo = await browser.nth(0)
    act(() => { chosen = result.current.panel.choose('anna') })
    const anna = await browser.nth(1)
    await act(async () => {
      anna.release()
      expect(await chosen).toBe(true)
      theo.release()
      expect(await again).toBe('superseded')
    })
    expect(browser.jar.shopper).toBe('anna')
    expect(await meSays()).toBe('anna')
    expect(result.current.persona.persona?.id).toBe('anna')
  })

  it('reports signed_in only once the session names that shopper', async () => {
    const { result } = mountBrowser()
    let again: Promise<unknown> = Promise.resolve('')
    act(() => { again = result.current.refreshSession('theo') })
    await act(async () => {
      ;(await browser.nth(0)).release()
      expect(await again).toBe('signed_in')
    })
    expect(result.current.auth.user?.username).toBe('theo')
  })

  it('reports failed, then signs in on a retry', async () => {
    const { result } = mountBrowser()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    let again: Promise<unknown> = Promise.resolve('')
    act(() => { again = result.current.refreshSession('theo') })
    await act(async () => {
      ;(await browser.nth(0)).refuse()
      expect(await again).toBe('failed')
    })
    expect(browser.jar.shopper).toBeNull()
    act(() => { again = result.current.refreshSession('theo') })
    await act(async () => {
      ;(await browser.nth(1)).release()
      expect(await again).toBe('signed_in')
    })
    expect(browser.jar.shopper).toBe('theo')
    warn.mockRestore()
  })
})
