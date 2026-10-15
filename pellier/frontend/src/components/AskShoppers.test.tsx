/**
 * Choosing a shopper in the Ask Pellier panel: four cards signed out, one row
 * once signed in. The four shoppers in lab order, a choice that is a real
 * sign-in followed by the edit, the shopper read from the verified session,
 * and Sign out back to the neutral store.
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

import { ShopperBar, ShopperCards } from './AskShoppers'

beforeEach(() => {
  vi.clearAllMocks()
  state.username = ''
  state.persona = null
})

describe('Choosing a shopper in the Ask Pellier panel', () => {
  it('offers the four shoppers as cards in lab order with their portraits, and never staff', () => {
    render(<ShopperCards />)
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

  it('says under the cards that the choice is a sign-in and the token is what counts', () => {
    render(<ShopperCards />)
    expect(screen.getByTestId('persona-identity-boundary')).toHaveTextContent(
      'Choosing a shopper signs you in with their demo account. Pellier trusts the signed token, not this choice.',
    )
  })

  it('signs in with the demo account first, then opens the edit', async () => {
    render(<ShopperCards />)
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
    render(<ShopperCards />)
    fireEvent.click(screen.getByTestId('ask-shopper-theo'))
    const error = await screen.findByTestId('persona-sign-in-error')
    expect(error).toHaveTextContent('That sign-in did not complete. Try again, or use the sign-in page.')
    expect(error).not.toHaveTextContent('workshop_sign_in_unavailable')
    expect(state.switchPersona).not.toHaveBeenCalled()
    expect(screen.getByTestId('ask-shopper-theo')).toHaveAttribute('aria-pressed', 'false')
    warn.mockRestore()
  })

  it('shows the shopper the server verified, not the edit on screen, in one row', () => {
    state.username = 'theo'
    state.persona = { id: 'anna' }
    render(<ShopperBar />)
    expect(screen.getByTestId('ask-signed-in-name')).toHaveTextContent('Theo')
    expect(screen.getByTestId('ask-shopper-theo')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('ask-shopper-anna')).toHaveAttribute('aria-pressed', 'false')
  })

  it('offers Choose a shopper, and the sign-in note, while nobody is signed in', () => {
    render(<ShopperBar />)
    expect(screen.getByTestId('ask-signed-in-name')).toHaveTextContent('Not signed in')
    expect(screen.queryByTestId('ask-sign-out')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('ask-switch-shopper'))
    expect(screen.getByTestId('ask-switch-shopper')).toHaveTextContent('Choose a shopper')
    expect(screen.getByTestId('persona-identity-boundary')).toBeVisible()
    fireEvent.click(screen.getByTestId('ask-shopper-theo'))
    expect(state.workshopSignIn).toHaveBeenCalledWith('theo', expect.any(AbortSignal))
  })

  it('keeps the other shoppers behind Switch shopper until asked', () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<ShopperBar />)
    const chips = screen.getByTestId('ask-shopper-marco').parentElement as HTMLElement
    const toggle = screen.getByTestId('ask-switch-shopper')
    expect(toggle).toHaveTextContent('Switch shopper')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(chips).not.toBeVisible()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(chips).toBeVisible()
    expect(within(chips).getAllByRole('button').map(chip => chip.textContent))
      .toEqual(['Anna', 'Marco', 'Theo', 'Jessica'])
  })

  it('folds the chips again once a switch has signed the new shopper in', async () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<ShopperBar />)
    fireEvent.click(screen.getByTestId('ask-switch-shopper'))
    fireEvent.click(screen.getByTestId('ask-shopper-marco'))
    await waitFor(() => expect(state.switchPersona).toHaveBeenCalledWith('marco'))
    await waitFor(() => expect(screen.getByTestId('ask-switch-shopper')).toHaveAttribute('aria-expanded', 'false'))
  })

  it('does not sign the same shopper in again once their edit is open', () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<ShopperBar />)
    fireEvent.click(screen.getByTestId('ask-switch-shopper'))
    fireEvent.click(screen.getByTestId('ask-shopper-anna'))
    expect(state.workshopSignIn).not.toHaveBeenCalled()
  })

  it('signs out from the row, back to the neutral store', () => {
    state.username = 'anna'
    state.persona = { id: 'anna' }
    render(<ShopperBar />)
    const signOut = screen.getByTestId('ask-sign-out')
    expect(signOut).toHaveTextContent('Sign out')
    fireEvent.click(signOut)
    expect(state.clearShopper).toHaveBeenCalledTimes(1)
    expect(state.logout).toHaveBeenCalledTimes(1)
  })
})
