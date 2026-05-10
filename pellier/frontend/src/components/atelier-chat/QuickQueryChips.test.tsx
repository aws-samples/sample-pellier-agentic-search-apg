/**
 * QuickQueryChips tests — post-turn "try asking" strip.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import QuickQueryChips from './QuickQueryChips'

describe('QuickQueryChips', () => {
  it('renders each query as a chip', () => {
    render(
      <QuickQueryChips
        queries={["what's low on stock", 'compare two shirts']}
        onPick={vi.fn()}
      />,
    )
    expect(screen.getByText(/what's low on stock/)).toBeInTheDocument()
    expect(screen.getByText(/compare two shirts/)).toBeInTheDocument()
  })

  it('calls onPick with the chip text on click', async () => {
    const onPick = vi.fn()
    const user = userEvent.setup()
    render(
      <QuickQueryChips
        queries={['return policy?']}
        onPick={onPick}
      />,
    )
    await user.click(screen.getByTestId('quick-query-chip-return policy?'))
    expect(onPick).toHaveBeenCalledWith('return policy?')
  })

  it('disables all chips when disabled is true', () => {
    render(
      <QuickQueryChips
        queries={['a', 'b']}
        onPick={vi.fn()}
        disabled
      />,
    )
    expect(screen.getByTestId('quick-query-chip-a')).toBeDisabled()
    expect(screen.getByTestId('quick-query-chip-b')).toBeDisabled()
  })
})
