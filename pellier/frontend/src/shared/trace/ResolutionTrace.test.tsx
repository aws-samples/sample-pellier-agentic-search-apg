import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResolutionTrace, { traceStatus, type ResolutionStep } from './ResolutionTrace'

const steps: ResolutionStep[] = [
  { id: 'read', title: 'Read catalog', status: 'completed', summary: 'Two pieces returned.', source: 'Aurora PostgreSQL' },
  { id: 'policy', title: 'Observe policy boundary', status: 'unknown', summary: 'NOT_EVALUATED' },
  { id: 'answer', title: 'Save answer', status: 'completed' },
]

afterEach(() => vi.useRealTimers())

describe('ResolutionTrace', () => {
  it('never advances live execution with elapsed presentation time', () => {
    vi.useFakeTimers()
    render(<ResolutionTrace mode="live" busy steps={[{ ...steps[0], status: 'running' }]} outcome={{ label: 'Saved' }} />)
    act(() => vi.advanceTimersByTime(10000))
    expect(screen.getByText('In progress')).toBeInTheDocument()
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Replay' })).not.toBeInTheDocument()
  })

  it('pauses a recording, resumes at the same step, and keeps its result inspectable', () => {
    vi.useFakeTimers()
    render(<ResolutionTrace mode="recorded" autoPlay steps={steps} outcome={{ label: 'Recorded answer', body: 'One recommendation.' }} />)
    act(() => vi.advanceTimersByTime(1100))
    expect(screen.getByText('Read catalog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    act(() => vi.advanceTimersByTime(10000))
    expect(screen.queryByText('Observe policy boundary')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    act(() => vi.advanceTimersByTime(1100))
    expect(screen.getByText('NOT_EVALUATED')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
    expect(screen.getByText('One recommendation.')).toBeInTheDocument()
    expect(screen.getByText('Read catalog')).toBeInTheDocument()
    expect(screen.getByText('Not established')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Replay' }))
    expect(screen.queryByText('One recommendation.')).not.toBeInTheDocument()
    expect(screen.getByText('0 / 3')).toBeInTheDocument()
  })

  it('does not confuse a missing policy decision or a build block with a permit or denial', () => {
    expect(traceStatus('not_enforced')).toBe('unknown')
    expect(traceStatus('NOT_EVALUATED')).toBe('unknown')
    expect(traceStatus('policy_denied')).toBe('denied')
    expect(traceStatus('blocked')).toBe('blocked')
    expect(traceStatus('unavailable')).toBe('unavailable')
  })
})
