/**
 * PersonaTransitionOverlay tests — sign-in / sign-out celebration.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PersonaTransitionOverlay from './PersonaTransitionOverlay'
import type { PersonaTransition } from '../contexts/PersonaContext'

// --- Mock PersonaContext -------------------------------------------------
// The component only reads `lastTransition` and calls `clearTransition`.
// Mocking the hook lets us drive transitions deterministically without
// spinning up the full provider + fetch path.

let mockTransition: PersonaTransition | null = null
const clearTransition = vi.fn(() => {
  mockTransition = null
})

vi.mock('../contexts/PersonaContext', async () => {
  const actual = await vi.importActual<object>('../contexts/PersonaContext')
  return {
    ...actual,
    usePersona: () => ({
      persona: mockTransition?.persona ?? null,
      switchPersona: vi.fn(),
      signOut: vi.fn(),
      switching: false,
      lastTransition: mockTransition,
      clearTransition,
    }),
  }
})

function marco(): PersonaTransition['persona'] {
  return {
    id: 'marco',
    display_name: 'Marco Silva',
    role_tag: '',
    avatar_color: '#000',
    avatar_initial: 'M',
    customer_id: 'cust-marco',
    stats: { visits: 5, orders: 7, last_seen_days: 21 },
  }
}

describe('PersonaTransitionOverlay', () => {
  beforeEach(() => {
    mockTransition = null
    clearTransition.mockClear()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when lastTransition is null', () => {
    const { container } = render(<PersonaTransitionOverlay />)
    // Portal mounts inside document.body, not the container.
    expect(document.body.textContent).not.toContain('Welcome back')
    expect(container.innerHTML).toBe('')
  })

  it('shows the sign-in card with the persona name and tagline', () => {
    mockTransition = { id: 1, kind: 'sign-in', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(/Welcome back, Marco\./)).toBeInTheDocument()
    expect(screen.getByText(/Your thread is still warm/)).toBeInTheDocument()
    expect(screen.getByText(/SIGNED IN/i)).toBeInTheDocument()
  })

  it('shows Theo-specific tagline on sign-in', () => {
    const theo: PersonaTransition['persona'] = {
      id: 'theo',
      display_name: 'Theo',
      role_tag: '',
      avatar_color: '#5a4535',
      avatar_initial: 'T',
      customer_id: 'cust-theo',
      stats: { visits: 8, orders: 4, last_seen_days: 14 },
    }
    mockTransition = { id: 10, kind: 'sign-in', persona: theo }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(/Welcome back, Theo\./)).toBeInTheDocument()
    expect(screen.getByText(/Quiet pieces, kept ready/)).toBeInTheDocument()
  })

  it('shows the sign-out card without a tagline', () => {
    mockTransition = { id: 2, kind: 'sign-out', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(/See you soon, Marco\./)).toBeInTheDocument()
    // Sign-out deliberately skips the persona tag line.
    expect(screen.queryByText(/Your thread is still warm/)).not.toBeInTheDocument()
    expect(screen.getByText(/SIGNED OUT/i)).toBeInTheDocument()
  })

  it('auto-dismisses after 2400ms on sign-in', () => {
    mockTransition = { id: 3, kind: 'sign-in', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(clearTransition).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(2399)
    })
    expect(clearTransition).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(2)
    })
    expect(clearTransition).toHaveBeenCalledTimes(1)
  })

  it('auto-dismisses after 1600ms on sign-out (shorter than sign-in)', () => {
    mockTransition = { id: 4, kind: 'sign-out', persona: marco() }
    render(<PersonaTransitionOverlay />)
    act(() => {
      vi.advanceTimersByTime(1599)
    })
    expect(clearTransition).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(2)
    })
    expect(clearTransition).toHaveBeenCalledTimes(1)
  })

  it('dismisses on click', async () => {
    mockTransition = { id: 5, kind: 'sign-in', persona: marco() }
    vi.useRealTimers() // userEvent needs real timers
    const user = userEvent.setup()
    render(<PersonaTransitionOverlay />)
    await user.click(screen.getByRole('status'))
    expect(clearTransition).toHaveBeenCalled()
  })
})
