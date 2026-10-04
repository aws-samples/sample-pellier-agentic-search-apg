/**
 * PersonaTransitionOverlay tests — shopper scenario transitions.
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
    hero_image: '/products/hero-marco.webp',
    hero_alt: 'Marco profile',
    hero_subheadline: 'Live Aurora profile.',
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
    expect(document.body.textContent).not.toContain('Viewing')
    expect(container.innerHTML).toBe('')
  })

  it('shows the selected scenario without claiming authentication', () => {
    mockTransition = { id: 1, kind: 'sign-in', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(/Viewing Marco\./)).toBeInTheDocument()
    expect(
      screen.getByText('Travel and utility, grounded in leather and linen.'),
    ).toBeInTheDocument()
    expect(screen.getByAltText('Marco Silva profile')).toBeInTheDocument()
    expect(screen.getByText(/SCENARIO SELECTED/i)).toBeInTheDocument()
    expect(screen.queryByText(/SIGNED IN/i)).not.toBeInTheDocument()
  })

  it.each([
    ['anna', 'Anna', 'Gifting and ceremony, expressed in silk and glass.'],
    ['theo', 'Theo', 'Slow living through craft, stoneware, and natural materials.'],
  ])('shows the %s-specific tagline on selection', (id, displayName, tagline) => {
    const persona: PersonaTransition['persona'] = {
      id,
      display_name: displayName,
      role_tag: '',
      avatar_color: '#5a4535',
      avatar_initial: displayName.charAt(0),
      customer_id: `cust-${id}`,
      hero_image: `/products/hero-${id}.webp`,
      hero_alt: `${displayName} profile`,
      hero_subheadline: 'Live Aurora profile.',
      stats: { visits: 8, orders: 4, last_seen_days: 14 },
    }
    mockTransition = { id: 10, kind: 'sign-in', persona }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(`Viewing ${displayName}.`)).toBeInTheDocument()
    expect(screen.getByText(tagline)).toBeInTheDocument()
  })

  it('shows the cleared scenario without a tagline', () => {
    mockTransition = { id: 2, kind: 'sign-out', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(screen.getByText(/Leaving Marco\./)).toBeInTheDocument()
    // Sign-out deliberately skips the persona tag line.
    expect(
      screen.queryByText('Travel and utility, grounded in leather and linen.'),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/SCENARIO CLEARED/i)).toBeInTheDocument()
  })

  it('auto-dismisses after 1100ms on sign-in', () => {
    mockTransition = { id: 3, kind: 'sign-in', persona: marco() }
    render(<PersonaTransitionOverlay />)
    expect(clearTransition).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(1099)
    })
    expect(clearTransition).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(2)
    })
    expect(clearTransition).toHaveBeenCalledTimes(1)
  })

  it('auto-dismisses after 800ms on sign-out (shorter than sign-in)', () => {
    mockTransition = { id: 4, kind: 'sign-out', persona: marco() }
    render(<PersonaTransitionOverlay />)
    act(() => {
      vi.advanceTimersByTime(799)
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
