import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TraceChip } from './TraceChip'

describe('TraceChip', () => {
  it('renders the trace as a label, not a link', () => {
    render(<TraceChip tool="memory.recall" />)

    const chip = screen.getByTestId('trace-chip-memory.recall')
    expect(chip).toHaveTextContent('memory.recall')
    expect(chip).not.toHaveAttribute('href')
  })
})
