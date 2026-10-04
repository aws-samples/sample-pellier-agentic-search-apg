/**
 * Choosing a shopper is a sign-in; signed out is the neutral store.
 *
 * The verified identity on the next turn is the server's (pinned by the backend's
 * `test_turn_principal.py`); here, what the browser does to get there: sign in,
 * re-read the session, then follow with the edit, and never the other way round.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  username: '' as string,
  loading: false,
  unavailable: false,
  persona: null as null | { id: string },
  refresh: vi.fn(() => Promise.resolve()),
  logout: vi.fn(),
  switchPersona: vi.fn(() => Promise.resolve(true)),
  clearPersona: vi.fn(),
  clearShopper: vi.fn(),
  workshopSignIn: vi.fn(() => Promise.resolve({ status: 'signed_in' })),
}))

vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: Boolean(state.username),
    loading: state.loading,
    authUnavailable: state.unavailable,
    user: state.username ? { sub: `sub-${state.username}`, email: 'e', username: state.username } : null,
    refresh: state.refresh,
    logout: state.logout,
  }),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: state.persona,
    switchPersona: state.switchPersona,
    clearPersona: state.clearPersona,
    signOut: state.clearShopper,
  }),
}))
vi.mock('../services/passwordAuth', async () => {
  const actual = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
  return { ...actual, workshopSignIn: state.workshopSignIn }
})

import { chooserShoppers, useNeutralWhenSignedOut, useShopperSignIn } from './useShopperSignIn'

beforeEach(() => {
  vi.clearAllMocks()
  state.username = ''
  state.loading = false
  state.unavailable = false
  state.persona = null
})

describe('choosing a shopper', () => {
  it('signs in, re-reads the session, then opens the edit, in that order', async () => {
    const { result } = renderHook(() => useShopperSignIn())
    await act(async () => { expect(await result.current.choose('theo')).toBe(true) })
    expect(state.workshopSignIn).toHaveBeenCalledWith('theo', expect.any(AbortSignal))
    expect(state.switchPersona).toHaveBeenCalledWith('theo')
    const order = [state.workshopSignIn, state.refresh, state.switchPersona].map(fn => fn.mock.invocationCallOrder[0])
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })

  it('switching performs a new sign-in for the next shopper', async () => {
    state.username = 'theo'
    state.persona = { id: 'theo' }
    const { result } = renderHook(() => useShopperSignIn())
    expect(result.current.signedInAs).toBe('theo')
    await act(async () => { await result.current.choose('anna') })
    expect(state.workshopSignIn).toHaveBeenCalledExactlyOnceWith('anna', expect.any(AbortSignal))
    expect(state.switchPersona).toHaveBeenCalledWith('anna')
  })

  it('keeps the previous edit when the sign-in fails', async () => {
    const { PasswordAuthError } = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
    state.workshopSignIn.mockRejectedValueOnce(new PasswordAuthError('auth_unavailable'))
    const { result } = renderHook(() => useShopperSignIn())
    await act(async () => { expect(await result.current.choose('marco')).toBe(false) })
    await waitFor(() => expect(result.current.error).toBe('auth_unavailable'))
    expect(state.switchPersona).not.toHaveBeenCalled()
  })

  it('names no verified shopper for staff or the signed-out state', () => {
    state.username = 'nadia'
    expect(renderHook(() => useShopperSignIn()).result.current.signedInAs).toBeNull()
    state.username = ''
    expect(renderHook(() => useShopperSignIn()).result.current.signedInAs).toBeNull()
  })

  it('signs out to the neutral store', () => {
    state.username = 'jessica'
    const { result } = renderHook(() => useShopperSignIn())
    act(() => result.current.signOut())
    expect(state.clearShopper).toHaveBeenCalledOnce()
    expect(state.logout).toHaveBeenCalledOnce()
  })

  it('offers only the four shoppers, in chooser order', () => {
    const listed = ['fresh', 'nadia', 'jessica', 'theo', 'anna', 'marco'].map(id => ({ id }))
    expect(chooserShoppers(listed).map(p => p.id)).toEqual(['marco', 'anna', 'theo', 'jessica'])
  })
})

describe('signed out is the neutral store', () => {
  it('clears an edit left from an ended session once the server says anonymous', () => {
    state.persona = { id: 'theo' }
    renderHook(() => useNeutralWhenSignedOut())
    expect(state.clearPersona).toHaveBeenCalledOnce()
  })

  it('clears nothing while the session is still being read, or when the check failed', () => {
    state.persona = { id: 'theo' }
    state.loading = true
    renderHook(() => useNeutralWhenSignedOut())
    state.loading = false
    state.unavailable = true
    renderHook(() => useNeutralWhenSignedOut())
    expect(state.clearPersona).not.toHaveBeenCalled()
  })

  it('keeps the edit of a signed-in shopper', () => {
    state.username = 'theo'
    state.persona = { id: 'theo' }
    renderHook(() => useNeutralWhenSignedOut())
    expect(state.clearPersona).not.toHaveBeenCalled()
  })
})
