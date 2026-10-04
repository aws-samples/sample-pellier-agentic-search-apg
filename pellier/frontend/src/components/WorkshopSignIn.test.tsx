/**
 * "Signed in as": one chip per demo shopper, a real sign-in behind each.
 *
 * The chip calls the server, re-reads the session, then selects the matching
 * scenario. Nadia has no chip. The pressed chip is the username the server
 * reported, never a guess from the scenario.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  authenticated: false,
  username: '' as string,
  refresh: vi.fn(() => Promise.resolve()),
  logout: vi.fn(),
  switchPersona: vi.fn(() => Promise.resolve(true)),
  workshopSignIn: vi.fn(() => Promise.resolve({ status: 'signed_in', username: 'anna', signInMethod: 'workshop' })),
}))

vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: state.authenticated,
    user: state.authenticated ? { sub: 'sub', email: `${state.username}@pellier.example.com`, username: state.username } : null,
    refresh: state.refresh,
    logout: state.logout,
  }),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({ switchPersona: state.switchPersona }),
}))
vi.mock('../services/passwordAuth', async () => {
  const actual = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
  return { ...actual, workshopSignIn: state.workshopSignIn }
})

import WorkshopSignIn from './WorkshopSignIn'

describe('WorkshopSignIn', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    state.authenticated = false
    state.username = ''
  })

  it('offers exactly the four shoppers and never a staff chip', () => {
    render(<WorkshopSignIn />)
    const chips = screen.getAllByRole('button', { pressed: false })
    expect(chips.map(chip => chip.textContent)).toEqual(['Anna', 'Marco', 'Theo', 'Jessica'])
    expect(screen.queryByRole('button', { name: /nadia/i })).not.toBeInTheDocument()
    expect(screen.getByText('Workshop sign-in (demo shoppers). Nadia signs in with her password on the Operator desk.')).toBeInTheDocument()
  })

  it('signs in on the server, re-reads the session, then selects the scenario', async () => {
    render(<WorkshopSignIn />)
    fireEvent.click(screen.getByTestId('workshop-sign-in-anna'))
    await waitFor(() => expect(state.switchPersona).toHaveBeenCalledWith('anna'))
    expect(state.workshopSignIn).toHaveBeenCalledWith('anna', expect.any(AbortSignal))
    expect(state.refresh).toHaveBeenCalledOnce()
    const order = [state.workshopSignIn, state.refresh, state.switchPersona].map(fn => fn.mock.invocationCallOrder[0])
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })

  it("keeps the neutral scenario for Jessica, who has none of her own", async () => {
    render(<WorkshopSignIn />)
    fireEvent.click(screen.getByTestId('workshop-sign-in-jessica'))
    await waitFor(() => expect(state.switchPersona).toHaveBeenCalledWith('fresh'))
    expect(state.workshopSignIn).toHaveBeenCalledWith('jessica', expect.any(AbortSignal))
  })

  it('presses the chip the server says is signed in, and offers sign out', () => {
    state.authenticated = true
    state.username = 'theo'
    render(<WorkshopSignIn />)
    expect(screen.getByTestId('workshop-sign-in-theo')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('workshop-sign-in-anna')).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(state.logout).toHaveBeenCalledOnce()
  })

  it('reports a refused sign-in without inventing a session', async () => {
    const { PasswordAuthError } = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
    state.workshopSignIn.mockRejectedValueOnce(new PasswordAuthError('workshop_user_not_allowed'))
    render(<WorkshopSignIn />)
    fireEvent.click(screen.getByTestId('workshop-sign-in-marco'))
    await screen.findByRole('alert')
    expect(screen.getByRole('alert')).toHaveTextContent('workshop_user_not_allowed')
    expect(state.refresh).not.toHaveBeenCalled()
    expect(state.switchPersona).not.toHaveBeenCalled()
  })
})
