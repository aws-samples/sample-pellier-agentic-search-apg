/**
 * PlanPreviewChip tests — PLAN summary chip in-chat.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import PlanPreviewChip from './PlanPreviewChip'

describe('PlanPreviewChip', () => {
  it('renders the step count and joined step chain', () => {
    render(
      <PlanPreviewChip
        stepCount={5}
        stepNames={['parse', 'memory', 'search', 'filter', 'synthesize']}
      />,
    )
    expect(screen.getByText('5 steps')).toBeInTheDocument()
    expect(
      screen.getByText(/parse → memory → search → filter → synthesize/),
    ).toBeInTheDocument()
  })

  it('fires onViewTrace when the trace link is clicked', async () => {
    const onViewTrace = vi.fn()
    const user = userEvent.setup()
    render(
      <PlanPreviewChip
        stepCount={3}
        stepNames={['a', 'b', 'c']}
        onViewTrace={onViewTrace}
      />,
    )
    await user.click(screen.getByTestId('plan-preview-view-trace'))
    expect(onViewTrace).toHaveBeenCalledOnce()
  })
})
