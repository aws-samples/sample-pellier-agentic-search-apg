/**
 * A shopper choice is one switch: the sign-in that names the shopper and the
 * persona that lands after it. Ask Pellier resets its draft when the persona
 * lands, so `switching` has to cover the whole span (e2e/shopper-sign-in.spec.ts
 * shows the panel side).
 */
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock('../services/apiBase', () => ({ apiFetch }))

import { PersonaProvider, usePersona } from './PersonaContext'

const ANNA = {
  id: 'anna', edit: 'anna', display_name: 'Anna', role_tag: "Anna's edit", avatar_color: '#5a4535',
  avatar_initial: 'A', customer_id: 'CUST-ANNA', hero_image: '', hero_alt: 'Anna', hero_subheadline: '',
  stats: { visits: 1, orders: 1, last_seen_days: 1 },
}

const wrapper = ({ children }: { children: ReactNode }) => <PersonaProvider>{children}</PersonaProvider>

beforeEach(() => {
  apiFetch.mockReset()
  localStorage.clear()
  sessionStorage.clear()
})

describe('switchPersona with a shopper sign-in', () => {
  it('stays switching from the sign-in until the persona lands', async () => {
    apiFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ session_id: 'persona-anna-1', persona: ANNA }) })
    const { result } = renderHook(() => usePersona(), { wrapper })
    let finishSignIn = () => {}
    let switched: Promise<boolean> = Promise.resolve(false)
    act(() => {
      switched = result.current.switchPersona('anna', () => new Promise<void>(resolve => { finishSignIn = resolve }))
    })
    expect(result.current.switching).toBe(true)
    expect(apiFetch).not.toHaveBeenCalled()

    await act(async () => {
      finishSignIn()
      expect(await switched).toBe(true)
    })
    expect(apiFetch).toHaveBeenCalledWith('/api/persona/switch', expect.objectContaining({ method: 'POST' }))
    expect(result.current.persona?.id).toBe('anna')
    expect(result.current.switching).toBe(false)
  })

  it('hands a failed sign-in back to the caller, opens nothing, and stops switching', async () => {
    const { result } = renderHook(() => usePersona(), { wrapper })
    const failure = new Error('workshop_sign_in_unavailable')
    await act(async () => {
      await expect(result.current.switchPersona('anna', () => Promise.reject(failure))).rejects.toBe(failure)
    })
    expect(apiFetch).not.toHaveBeenCalled()
    expect(result.current.persona).toBeNull()
    expect(result.current.switchError).toBeNull()
    expect(result.current.switching).toBe(false)
  })
})

describe('the mount-time rehydrate', () => {
  const current = (persona: typeof ANNA) => ({ ok: true, status: 200, json: async () => ({ persona }) })

  function slowRehydrate() {
    localStorage.setItem('pellier-session-id', 'persona-old-1')
    let answer: (value: unknown) => void = () => {}
    apiFetch.mockImplementation((path: string) => {
      if (String(path).startsWith('/api/persona/current')) {
        return new Promise(resolve => { answer = resolve })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ session_id: 'persona-anna-1', persona: ANNA }) })
    })
    return (persona: typeof ANNA) => answer(current(persona))
  }

  it('does not overwrite a shopper chosen before it answers', async () => {
    const answerLate = slowRehydrate()
    const { result } = renderHook(() => usePersona(), { wrapper })
    await act(async () => { await result.current.switchPersona('anna') })
    expect(result.current.persona?.id).toBe('anna')

    await act(async () => { answerLate({ ...ANNA, id: 'marco', display_name: 'Marco' }) })
    expect(result.current.persona?.id).toBe('anna')
  })

  it('does not bring a shopper back after sign-out before it answers', async () => {
    const answerLate = slowRehydrate()
    const { result } = renderHook(() => usePersona(), { wrapper })
    act(() => { result.current.clearPersona() })

    await act(async () => { answerLate(ANNA) })
    expect(result.current.persona).toBeNull()
  })
})

describe('startNewConversation', () => {
  const THEO = { ...ANNA, id: 'theo', display_name: 'Theo', role_tag: "Theo's edit", avatar_initial: 'T', customer_id: 'CUST-THEO' }
  const FIRST = `persona-theo-${'a'.repeat(32)}`
  const SECOND = `persona-theo-${'b'.repeat(32)}`
  const answer = (sessionId: string) => ({ ok: true, status: 200, json: async () => ({ session_id: sessionId, persona: THEO }) })

  async function signedInAsTheo() {
    apiFetch.mockResolvedValueOnce(answer(FIRST))
    const hook = renderHook(() => usePersona(), { wrapper })
    await act(async () => { await hook.result.current.switchPersona('theo') })
    localStorage.setItem('pellier-drawer-storefront', '[{"role":"user","content":"indigo linen"}]')
    localStorage.setItem('pellier-cart-session', FIRST)
    return hook
  }

  it('keeps the shopper signed in, takes a fresh server session and drops the saved thread', async () => {
    const { result } = await signedInAsTheo()
    const signIn = result.current.lastTransition
    apiFetch.mockResolvedValueOnce(answer(SECOND))
    let started = false
    await act(async () => { started = await result.current.startNewConversation() })
    expect(started).toBe(true)
    expect(apiFetch).toHaveBeenLastCalledWith('/api/persona/switch', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ persona_id: 'theo', current_session_id: FIRST }),
    }))
    expect(localStorage.getItem('pellier-session-id')).toBe(SECOND)
    expect(localStorage.getItem('pellier-drawer-storefront')).toBeNull()
    // The bag belongs to the shopper, not the conversation.
    expect(localStorage.getItem('pellier-cart-session')).toBe(SECOND)
    expect(result.current.persona?.id).toBe('theo')
    expect(result.current.conversation).toBe(1)
    expect(result.current.lastTransition).toBe(signIn)
    expect(result.current.newConversationFailed).toBe(false)
  })

  it('leaves the current conversation usable when no new session can be had', async () => {
    const { result } = await signedInAsTheo()
    apiFetch.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
    let started = true
    await act(async () => { started = await result.current.startNewConversation() })
    expect(started).toBe(false)
    expect(localStorage.getItem('pellier-session-id')).toBe(FIRST)
    expect(localStorage.getItem('pellier-drawer-storefront')).not.toBeNull()
    expect(result.current.conversation).toBe(0)
    expect(result.current.newConversationFailed).toBe(true)
    expect(result.current.persona?.id).toBe('theo')
  })

  it('refuses a session for another shopper', async () => {
    const { result } = await signedInAsTheo()
    apiFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ session_id: `persona-anna-${'c'.repeat(32)}`, persona: ANNA }) })
    await act(async () => { expect(await result.current.startNewConversation()).toBe(false) })
    expect(localStorage.getItem('pellier-session-id')).toBe(FIRST)
    expect(result.current.newConversationFailed).toBe(true)
  })

  it('drops a new session that lands after the shopper signed out', async () => {
    const { result } = await signedInAsTheo()
    let land: (value: unknown) => void = () => {}
    apiFetch.mockImplementationOnce(() => new Promise(resolve => { land = resolve }))
    let pending: Promise<boolean> = Promise.resolve(true)
    act(() => { pending = result.current.startNewConversation() })
    act(() => result.current.signOut())
    await act(async () => {
      land(answer(SECOND))
      expect(await pending).toBe(false)
    })
    expect(localStorage.getItem('pellier-session-id')).toBeNull()
    expect(result.current.conversation).toBe(0)
    expect(result.current.persona).toBeNull()
  })

  it('drops a new session that lands after another shopper was chosen', async () => {
    const { result } = await signedInAsTheo()
    let land: (value: unknown) => void = () => {}
    apiFetch.mockImplementationOnce(() => new Promise(resolve => { land = resolve }))
    let pending: Promise<boolean> = Promise.resolve(true)
    act(() => { pending = result.current.startNewConversation() })
    const annaSession = `persona-anna-${'d'.repeat(32)}`
    apiFetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ session_id: annaSession, persona: ANNA }) })
    await act(async () => { await result.current.switchPersona('anna') })
    await act(async () => {
      land(answer(SECOND))
      expect(await pending).toBe(false)
    })
    expect(localStorage.getItem('pellier-session-id')).toBe(annaSession)
    expect(result.current.persona?.id).toBe('anna')
    expect(result.current.conversation).toBe(0)
    expect(result.current.newConversationFailed).toBe(false)
  })

  it('drops a late new session after a sign-out even when no session id was stored', async () => {
    const { result } = await signedInAsTheo()
    localStorage.removeItem('pellier-session-id')
    let land: (value: unknown) => void = () => {}
    apiFetch.mockImplementationOnce(() => new Promise(resolve => { land = resolve }))
    let pending: Promise<boolean> = Promise.resolve(true)
    act(() => { pending = result.current.startNewConversation() })
    act(() => result.current.signOut())
    await act(async () => {
      land(answer(SECOND))
      expect(await pending).toBe(false)
    })
    expect(localStorage.getItem('pellier-session-id')).toBeNull()
    expect(result.current.conversation).toBe(0)
  })

  it('does nothing without a signed-in shopper', async () => {
    const { result } = renderHook(() => usePersona(), { wrapper })
    await act(async () => { expect(await result.current.startNewConversation()).toBe(false) })
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
