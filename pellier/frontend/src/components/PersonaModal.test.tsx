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
]

const switchPersona = vi.hoisted(() => vi.fn().mockResolvedValue(true))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: null,
    switchPersona,
    signOut: vi.fn(),
    switching: false,
  }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubPersonaFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIVE_PERSONAS), {
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
    await screen.findByTestId('persona-card-theo')

    const close = screen.getByTestId('persona-modal-close')
    const last = screen.getByTestId('persona-card-theo')

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
  it('titles itself as a scenario choice rather than a sign-in', async () => {
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

    expect(screen.getByRole('dialog')).toHaveAccessibleName('Choose a scenario')
    await waitFor(() => {
      expect(screen.getByTestId('persona-card-marco')).toBeInTheDocument()
    })
    expect(screen.queryByText(/sign in/i)).not.toBeInTheDocument()
  })

  it('uses the shared Marco, Anna, and Theo headshots', async () => {
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

describe('PersonaModal switch recovery', () => {
  it('stays open when the server cannot switch profiles, then closes on success', async () => {
    stubPersonaFetch()
    switchPersona.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<PersonaModal open onClose={onClose} />)
    const profile = await screen.findByTestId('persona-card-marco')
    await user.click(profile)
    expect(onClose).not.toHaveBeenCalled()
    await user.click(profile)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })
})
