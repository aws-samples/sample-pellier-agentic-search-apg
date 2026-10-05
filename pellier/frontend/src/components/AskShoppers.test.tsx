/**
 * "Signed in as" in the Ask Pellier panel: the four shoppers in lab order,
 * a choice that is a real sign-in followed by the edit, the selected chip
 * read from the verified session, and Sign out back to the neutral store.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  username: '' as string,
  persona: null as null | { id: string },
  refresh: vi.fn(() => Promise.resolve()),
  logout: vi.fn(),
  switchPersona: vi.fn(() => Promise.resolve(true)),
  clearShopper: vi.fn(),
  workshopSignIn: vi.fn(() => Promise.resolve({ status: 'signed_in' })),
}))

vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: Boolean(state.username),
    loading: false,
    authUnavailable: false,
    user: state.username ? { sub: `sub-${state.username}`, email: 'e', username: state.username } : null,
    refresh: state.refresh,
    logout: state.logout,
  }),
}))
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: state.persona,
    switchPersona: state.switchPersona,
    signOut: state.clearShopper,
    switching: false,
    switchError: null,
  }),
}))
vi.mock('../services/passwordAuth', async () => {
  const actual = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
  return { ...actual, workshopSignIn: state.workshopSignIn }
})

import AskShoppers from './AskShoppers'

beforeEach(() => {
  vi.clearAllMocks()
  state.username = ''
  state.persona = null
})

describe('Signed in as, in the Ask Pellier panel', () => {
  it('offers the four shoppers in lab order with their portraits, and never staff', () => {
    render(<AskShoppers />)
    const group = screen.getByRole('group', { name: 'Signed in as' })
    const chips = within(group).getAllByRole('button')
    expect(chips.map(chip => chip.textContent)).toEqual(['Anna', 'Marco', 'Theo', 'Jessica'])
    for (const chip of chips) {
      expect(chip).toHaveAttribute('aria-pressed', 'false')
      expect(chip.querySelector('img')?.getAttribute('src')).toMatch(/\/assets\/personas\/\w+-720\.webp$/)
    }
    expect(screen.queryByTestId('ask-shopper-nadia')).not.toBeInTheDocument()
    expect(screen.queryByTestId('ask-sign-out')).not.toBeInTheDocument()
  })

  it('says under the chips that the choice is a sign-in and the token is what counts', () => {
    render(<AskShoppers />)
    expect(screen.getByTestId('persona-identity-boundary')).toHaveTextContent(
      'Choosing a shopper signs you in with their demo account. Pellier trusts the signed token, not this choice.',
    )
  })

  it('signs in with the demo account first, then opens the edit', async () => {
    render(<AskShoppers />)
    fireEvent.click(screen.getByTestId('ask-shopper-jessica'))
    await waitFor(() => expect(state.switchPersona).toHaveBeenCalledWith('jessica'))
    expect(state.workshopSignIn).toHaveBeenCalledWith('jessica', expect.any(AbortSignal))
    expect(state.workshopSignIn.mock.invocationCallOrder[0])
      .toBeLessThan(state.switchPersona.mock.invocationCallOrder[0])
  })

  it('selects no edit when the sign-in fails, and says so in a plain sentence', async () => {
    const { PasswordAuthError } = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
    state.workshopSignIn.mockRejectedValueOnce(new PasswordAuthError('workshop_sign_in_unavailable'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    render(<AskShoppers />)
    fireEvent.click(screen.getByTestId('ask-shopper-theo'))
    const error = await screen.findByTestId('persona-sign-in-error')
    expect(error).toHaveTextContent('That sign-in did not complete. Try again, or use the sign-in page.')
    expect(error).not.toHaveTextContent('workshop_sign_in_unavailable')
    expect(state.switchPersona).not.toHaveBeenCalled()
    expect(screen.getByTestId('ask-shopper-theo')).toHaveAttribute('aria-pressed', 'false')
    warn.mockRestore()
  })

  it('marks the shopper the server verified, not the edit on screen', () => {
    state.username = 'theo'
    state.persona = { id: 'anna' }
    render(<AskShoppers />)
    expect(screen.getByTestId('ask-shopper-theo')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('ask-shopper-anna')).toHaveAttribute('aria-pressed', 'false')
  })

  it('does not sign the same shopper in again once their edit is open', () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<AskShoppers />)
    fireEvent.click(screen.getByTestId('ask-shopper-anna'))
    expect(state.workshopSignIn).not.toHaveBeenCalled()
  })

  it('signs out from the end of the row, back to the neutral store', () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<AskShoppers />)
    const signOut = screen.getByTestId('ask-sign-out')
    expect(signOut).toHaveTextContent('Sign out')
    expect(within(screen.getByRole('group', { name: 'Signed in as' })).getAllByRole('button').at(-1)).toBe(signOut)
    fireEvent.click(signOut)
    expect(state.clearShopper).toHaveBeenCalledTimes(1)
    expect(state.logout).toHaveBeenCalledTimes(1)
  })
})
