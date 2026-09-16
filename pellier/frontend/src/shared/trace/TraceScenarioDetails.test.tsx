import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import examples from '../../data/pellierTraceScenarios.json'
import { WORKSHOP_JOURNEYS, type WorkshopAnchorId } from '../../data/workshopJourneys'
import { findLabExercise } from '../../observatory/labs/labCatalog'
import TraceScenarioDetails from './TraceScenarioDetails'

describe('recorded persona evidence', () => {
  it('uses the exact canonical prompts for the recorded journey turns', () => {
    for (const example of examples) {
      const journey = WORKSHOP_JOURNEYS[example.learning.anchorId as WorkshopAnchorId]
      expect(findLabExercise(example.learning.labId)).toBeDefined()
      if (example.learning.turnIndex != null) {
        expect(example.request).toBe(journey.prompts[example.learning.turnIndex])
      }
    }
  })

  it('labels source SQL and measurement scope, without claiming zero model calls', () => {
    render(<MemoryRouter><TraceScenarioDetails example={examples[0]} /></MemoryRouter>)
    expect(screen.getByText('277 ms · SQL read')).toBeInTheDocument()
    expect(screen.getByText('2 specialist chat spans recorded')).toBeInTheDocument()
    expect(screen.getByLabelText('Source SQL excerpt · vector lookup')).toHaveTextContent('embedding <=>')
    expect(screen.getByText(/Category filtering happens in the tool after this baseline query/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Marco’s exercise' })).toHaveAttribute('href', '/observatory/workbench?lab=grounded-inventory')
    expect(screen.getByText(/does not complete that exercise/)).toBeInTheDocument()
  })

  it('links Jessica’s actual investigation to her guided Operator case', () => {
    render(<MemoryRouter><TraceScenarioDetails example={examples[1]} /></MemoryRouter>)
    expect(screen.getByText('5 orders · 1 ticket · 1 return · 0 proposed actions')).toBeInTheDocument()
    expect(screen.getByLabelText('Source SQL · authoritative returns')).toHaveTextContent('WHERE r.customer_id = %s')
    expect(screen.getByRole('link', { name: 'Open the guided Operator turns' })).toHaveAttribute('href', '/operator/clients/CUST-JESSICA?guided=service-recovery#operator-concierge-title')
    expect(screen.getByText(/combined read, not this statement alone/)).toBeInTheDocument()
  })

  it('keeps missing timing, historical policy, and unlinked execution distinct', () => {
    render(<MemoryRouter><TraceScenarioDetails example={examples[2]} /></MemoryRouter>)
    expect(screen.getByText('Timing not recorded')).toBeInTheDocument()
    expect(screen.getByText('Not recorded')).toBeInTheDocument()
    expect(screen.getByLabelText('Recorded policy receipt · public fields')).toHaveTextContent('"audit_id": null')
    expect(screen.getByText(/do not isolate which condition caused the denial/)).toBeInTheDocument()
    expect(screen.getByText(/Current policy configuration may differ/)).toBeInTheDocument()
  })
})
