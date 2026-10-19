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
