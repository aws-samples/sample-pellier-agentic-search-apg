import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getPersonaModalPortrait } from '../data/personaPhotos'
import PersonaModal from './PersonaModal'

const LIVE_PERSONAS = [
  {
    id: 'marco',
    display_name: 'Marco',
    role_tag: 'Returning',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a3528',
    avatar_initial: 'M',
    stats: { visits: 11, orders: 7, last_seen_days: 21 },
  },
  {
    id: 'anna',
    display_name: 'Anna',
    role_tag: 'Gift-giver',
    blurb: 'Live Aurora profile.',
    avatar_color: '#6b3d2a',
    avatar_initial: 'A',
    stats: { visits: 6, orders: 5, last_seen_days: 9 },
  },
  {
    id: 'theo',
    display_name: 'Theo',
    role_tag: 'Home + slow craft',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5a4535',
    avatar_initial: 'T',
    stats: { visits: 8, orders: 4, last_seen_days: 14 },
  },
  {
    id: 'jessica',
    display_name: 'Jessica',
    role_tag: 'Home comforts, bath, soft light',
    blurb: 'Live Aurora profile.',
    avatar_color: '#5b4a3c',
    avatar_initial: 'J',
    stats: { visits: 5, orders: 5, last_seen_days: 6 },
  },
]

// What the profile read may also hold: the guest edit, and a staff name that
// must never become a choice.
const NOT_SHOPPERS = [
  { ...LIVE_PERSONAS[0], id: 'fresh', display_name: 'Pellier guest' },
  { ...LIVE_PERSONAS[0], id: 'nadia', display_name: 'Nadia' },
]

const state = vi.hoisted(() => ({
  switchPersona: vi.fn().mockResolvedValue(true),
  clearShopper: vi.fn(),
  refresh: vi.fn(() => Promise.resolve()),
  logout: vi.fn(),
  workshopSignIn: vi.fn(() => Promise.resolve({ status: 'signed_in' })),
  username: '',
}))
const switchPersona = state.switchPersona

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: null,
    switchPersona: state.switchPersona,
    signOut: state.clearShopper,
    switching: false,
  }),
}))
vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    isAuthenticated: Boolean(state.username),
    user: state.username ? { sub: 's', email: 'e', username: state.username } : null,
    refresh: state.refresh,
    logout: state.logout,
  }),
}))
vi.mock('../services/passwordAuth', async () => {
  const actual = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
  return { ...actual, workshopSignIn: state.workshopSignIn }
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  state.username = ''
})

function stubPersonaFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify([...NOT_SHOPPERS, ...LIVE_PERSONAS]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

describe('PersonaModal keyboard and focus', () => {
  it('closes on Escape', async () => {
    stubPersonaFetch()
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PersonaModal open onClose={onClose} />)
    await screen.findByTestId('persona-card-marco')

    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('wraps Tab and Shift+Tab inside the dialog', async () => {
    stubPersonaFetch()
    const user = userEvent.setup()
    render(<PersonaModal open onClose={vi.fn()} />)
    await screen.findByTestId('persona-card-jessica')

    const close = screen.getByTestId('persona-modal-close')
    const last = screen.getByTestId('persona-card-jessica')

    last.focus()
    await user.keyboard('{Tab}')
    expect(close).toHaveFocus()

    await user.keyboard('{Shift>}{Tab}{/Shift}')
    expect(last).toHaveFocus()
  })

  it('returns focus to the opener when it closes', async () => {
    stubPersonaFetch()
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" data-testid="opener" onClick={() => setOpen(true)}>
            Open
          </button>
          <PersonaModal open={open} onClose={() => setOpen(false)} />
        </>
      )
    }
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByTestId('opener')

    await user.click(opener)
    await screen.findByTestId('persona-card-marco')
    await user.click(screen.getByTestId('persona-modal-close'))

    await waitFor(() => expect(opener).toHaveFocus())
  })
})

describe('PersonaModal', () => {
  it('offers the four shoppers, never staff, and says the choice is a sign-in', async () => {
    stubPersonaFetch()
    render(<PersonaModal open onClose={vi.fn()} />)

    expect(screen.getByRole('dialog')).toHaveAccessibleName('Choose a shopper')
    await screen.findByTestId('persona-card-marco')
    const cards = screen.getAllByRole('button').filter(b => b.dataset.persona)
    expect(cards.map(card => card.dataset.persona)).toEqual(['anna', 'marco', 'theo', 'jessica'])
    expect(screen.queryByTestId('persona-card-nadia')).not.toBeInTheDocument()
    expect(screen.queryByTestId('persona-card-fresh')).not.toBeInTheDocument()
    expect(screen.getByText(
      'Choosing a shopper signs you in with their demo account. Pellier trusts the signed token, not this choice.',
    )).toBeInTheDocument()
  })

  it('names the verified shopper and signs out back to the neutral store', async () => {
    stubPersonaFetch()
    state.username = 'theo'
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PersonaModal open onClose={onClose} />)
    await screen.findByTestId('persona-card-theo')
    expect(screen.getByText('Theo', { selector: 'strong' })).toBeInTheDocument()
    await user.click(screen.getByTestId('persona-sign-out'))
    expect(state.clearShopper).toHaveBeenCalledOnce()
    expect(state.logout).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('uses the shared shopper headshots', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify(LIVE_PERSONAS), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    render(<PersonaModal open onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('persona-card-marco')).toBeInTheDocument()
    })

    for (const persona of LIVE_PERSONAS) {
      const image = screen
        .getByTestId(`persona-card-${persona.id}`)
        .querySelector<HTMLImageElement>('.pm-avatar-photo')

      expect(image).not.toBeNull()
      expect(image).toHaveAttribute('src', getPersonaModalPortrait(persona.id))
      expect(image).toHaveAttribute('width', '1200')
      expect(image).toHaveAttribute('height', '1800')
    }
    expect(screen.queryByText('v1.0')).not.toBeInTheDocument()
  })
})

describe('PersonaModal choosing a shopper', () => {
  it('signs the shopper in, re-reads the session, then selects their edit', async () => {
    stubPersonaFetch()
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PersonaModal open onClose={onClose} />)
    await user.click(await screen.findByTestId('persona-card-jessica'))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(state.workshopSignIn).toHaveBeenCalledWith('jessica', expect.any(AbortSignal))
    expect(switchPersona).toHaveBeenCalledWith('jessica')
    const order = [state.workshopSignIn, state.refresh, switchPersona].map(fn => fn.mock.invocationCallOrder[0])
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })

  it('stays open and says so when the sign-in fails, then closes on success', async () => {
    const { PasswordAuthError } = await vi.importActual<typeof import('../services/passwordAuth')>('../services/passwordAuth')
    stubPersonaFetch()
    state.workshopSignIn.mockRejectedValueOnce(new PasswordAuthError('workshop_sign_in_unavailable'))
    const user = userEvent.setup()
    const onClose = vi.fn()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    render(<PersonaModal open onClose={onClose} />)
    const profile = await screen.findByTestId('persona-card-marco')
    await user.click(profile)
    const error = await screen.findByTestId('persona-modal-sign-in-error')
    expect(error).toHaveTextContent('That sign-in did not complete. Try again, or use the sign-in page.')
    expect(error).not.toHaveTextContent('workshop_sign_in_unavailable')
    expect(warn).toHaveBeenCalledWith('Shopper sign-in did not complete:', 'workshop_sign_in_unavailable')
    expect(switchPersona).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    await user.click(profile)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    warn.mockRestore()
  })

  it("marks the session's shopper as current, and opens an edit that failed to open", async () => {
    // Theo's sign-in succeeded and opening his edit failed: no edit is on screen.
    stubPersonaFetch()
    state.username = 'theo'
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PersonaModal open onClose={onClose} />)
    const theo = await screen.findByTestId('persona-card-theo')
    expect(theo).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('persona-card-marco')).toHaveAttribute('aria-pressed', 'false')
    await user.click(theo)
    await waitFor(() => expect(switchPersona).toHaveBeenCalledWith('theo'))
    expect(state.workshopSignIn).toHaveBeenCalledWith('theo', expect.any(AbortSignal))
  })
})
