import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ConciergePendingTurn from './ConciergePendingTurn'
import ConciergeInvestigation from './ConciergeInvestigation'
import { upsertInvestigationStep } from './traceSteps'
import type { ConciergeInvestigationStep, ConciergeStreamAnswer } from '../../services/operatorConcierge'

const steps: ConciergeInvestigationStep[] = [
  { kind: 'read', label: 'Read the client record', source: 'Aurora PostgreSQL', status: 'complete', durationMs: 40, result: 'The recorded orders were returned.' },
  { kind: 'recall', label: 'Recall prior context', source: 'AgentCore Memory', status: 'running' },
]
const answer: ConciergeStreamAnswer = { sessionId: 's1', turnId: 't1', status: 'complete', replayed: false, summary: 'Done.' }

describe('Operator trace', () => {
  it('retains numbered evidence after the answer and keeps approval separate', () => {
    const { rerender } = render(<ConciergePendingTurn request="Investigate" steps={steps} answer={null} />)
    expect(screen.getByLabelText('Step 1')).toBeInTheDocument()
    expect(screen.getByText('In progress')).toBeInTheDocument()
    rerender(<ConciergePendingTurn request="Investigate" steps={steps} answer={answer} />)
    expect(screen.getByText('Read the client record')).toBeInTheDocument()
    expect(screen.getByText('The recorded orders were returned.')).toBeInTheDocument()
    expect(screen.getByText(/separate review and approval controls/)).toBeInTheDocument()
    // An answer does not turn an uncompleted event into a success.
    expect(screen.getByText('In progress')).toBeInTheDocument()
  })
  it('preserves an earlier step being read while later events arrive', () => {
    const { rerender } = render(<ConciergePendingTurn request="Investigate" steps={steps} answer={null} />)
    const first = screen.getByRole('button', { name: /Step 1 Read the client record/ })
    fireEvent.click(first)
    expect(first).toHaveAttribute('aria-expanded', 'true')
    rerender(<ConciergePendingTurn request="Investigate" steps={[...steps, { kind: 'write', label: 'Save answer', source: 'Aurora', status: 'running' }]} answer={null} />)
    expect(first).toHaveAttribute('aria-expanded', 'true')
  })
  it('updates a late completion in place without changing the next step number', () => {
    const updated = upsertInvestigationStep(steps, { ...steps[0], status: 'failed' })
    expect(updated.map(step => step.kind)).toEqual(['read', 'recall'])
    expect(updated[0].status).toBe('failed')
    expect(updated[1]).toBe(steps[1])
  })
  it('distinguishes a completed read from an action awaiting human review', () => {
    const { rerender } = render(<ConciergeInvestigation steps={steps}
      orchestration={{ status: 'complete', checkpoint: { state: 'READ_ONLY_COMPLETE' } }} />)
    expect(screen.getByText('Read-only investigation complete')).toBeInTheDocument()
    expect(screen.getByText('No business action was proposed by this turn.')).toBeInTheDocument()
    expect(screen.queryByText('Waiting for human review')).not.toBeInTheDocument()
    rerender(<ConciergeInvestigation steps={steps}
      orchestration={{ status: 'complete', checkpoint: { state: 'WAITING_FOR_HUMAN' } }} />)
    expect(screen.getByText('Waiting for human review')).toBeInTheDocument()
    expect(screen.queryByText('No business action was proposed by this turn.')).not.toBeInTheDocument()
  })
})
