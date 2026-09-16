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
    fireEvent.click(screen.getByRole('button', { name: 'View all three' }))
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

  it('reads as one sequence, with each chapter naming what it adds to the last', () => {
    const { container } = renderLoop()
    expect([...container.querySelectorAll('.trace-scenario-tabs button')].map(b => b.textContent))
      .toEqual(['01Ground the answer', '02Bring in a person', '03Refuse the crossing'])

    // The opening chapter adds a layer but is not built on anything.
    expect(screen.getByText(examples[0].adds)).toBeInTheDocument()
    expect(examples[0].buildsOn).toBeNull()
    expect(container.querySelector('.trace-scenario-builds')).toBeNull()

    for (const example of examples.slice(1)) {
      fireEvent.click(screen.getByRole('button', { name: example.chapter }))
      expect(screen.getByText(example.adds)).toBeInTheDocument()
      // Every later chapter states the one it layers onto, by its number.
      expect(example.buildsOn).toMatch(/^0[12] /)
      expect(screen.getByText(example.buildsOn!)).toBeInTheDocument()
    }
  })

  it('names every scenario as recorded playback rather than a live request', () => {
    renderLoop()
    fireEvent.click(screen.getByRole('button', { name: 'View all three' }))
    expect(screen.getAllByText('Recorded playback')).toHaveLength(examples.length)
    expect(screen.queryByText('Live activity')).not.toBeInTheDocument()
  })
})
