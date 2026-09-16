import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import examples from '../../data/pellierTraceScenarios.json'
import TraceScenarioLoop from './TraceScenarioLoop'

function renderLoop() {
  return render(<MemoryRouter><TraceScenarioLoop /></MemoryRouter>)
}

describe('TraceScenarioLoop', () => {
  it('opens each recorded source excerpt inside the step it was drawn from', () => {
    const { container } = renderLoop()
    fireEvent.click(screen.getByRole('button', { name: 'View all examples' }))
    const expected: Record<string, string> = {
      catalog: 'embedding <=>',
      history: 'WHERE r.customer_id = %s',
      policy: '"audit_id": null',
    }
    for (const example of examples) {
      const stepId = example.inspection.codeStepId
      const step = container.querySelector<HTMLElement>(`[data-step-id="${stepId}"]`)
      expect(step, `${example.id} carries step ${stepId}`).not.toBeNull()
      // Collapsed until asked for, then the excerpt is in the step itself.
      expect(within(step!).queryByLabelText(example.inspection.codeLabel)).toBeNull()
      fireEvent.click(within(step!).getAllByRole('button')[0])
      expect(within(step!).getByLabelText(example.inspection.codeLabel))
        .toHaveTextContent(expected[stepId])
      expect(within(step!).getByText(example.inspection.codeNote)).toBeInTheDocument()
    }
  })

  it('names every scenario as recorded playback rather than a live request', () => {
    renderLoop()
    fireEvent.click(screen.getByRole('button', { name: 'View all examples' }))
    expect(screen.getAllByText('Recorded playback')).toHaveLength(examples.length)
    expect(screen.queryByText('Live activity')).not.toBeInTheDocument()
  })
})
