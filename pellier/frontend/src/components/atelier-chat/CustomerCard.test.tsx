/**
 * CustomerCard tests — top-of-chat identity strip.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import CustomerCard from './CustomerCard'

describe('CustomerCard', () => {
  it('renders the name, sublabel, and initial', () => {
    render(
      <CustomerCard
        name="Marco"
        sublabel="3 prior orders · warm neutrals"
        sessionId="39b5f398abc"
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByText('Marco')).toBeInTheDocument()
    expect(screen.getByText(/3 prior orders/)).toBeInTheDocument()
    // Initial (first letter, uppercase) sits in its own avatar circle
    // at the start of the card.
    const card = screen.getByTestId('customer-card')
    expect(card.textContent?.startsWith('M')).toBe(true)
  })

  it('truncates session id to first 8 chars for display', () => {
    render(
      <CustomerCard
        name="Anonymous"
        sessionId="39b5f398fedcba9876"
        onReset={vi.fn()}
      />,
    )
    expect(screen.getByText('39b5f398')).toBeInTheDocument()
    expect(screen.queryByText(/fedcba/)).not.toBeInTheDocument()
  })

  it('calls onReset when the New session button is clicked', async () => {
    const onReset = vi.fn()
    const user = userEvent.setup()
    render(<CustomerCard name="Marco" sessionId="abc" onReset={onReset} />)
    await user.click(screen.getByTestId('customer-card-reset'))
    expect(onReset).toHaveBeenCalledOnce()
  })

  it('disables the reset button when disabled is set', () => {
    render(
      <CustomerCard
        name="Marco"
        sessionId="abc"
        onReset={vi.fn()}
        disabled
      />,
    )
    expect(screen.getByTestId('customer-card-reset')).toBeDisabled()
  })
})
