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

  it('shows the whole recorded shape up front in showcase, with unreached steps inert', () => {
    vi.useFakeTimers()
    const { container } = render(
      <ResolutionTrace mode="recorded" variant="showcase" autoPlay steps={steps} />,
    )
    // Every title is present before playback reaches it, so the panel never
    // reserves height for rows it is not showing.
    expect(screen.getByText('Save answer')).toBeInTheDocument()
    const last = container.querySelector('[data-step-id="answer"]')
    expect(last).toHaveAttribute('data-reached', 'false')
    expect(last?.querySelector('button')).toBeDisabled()
    // An unreached step exposes no result text, states no outcome, and is
    // hidden from assistive tech.
    expect(screen.queryByText('NOT_EVALUATED')).not.toBeInTheDocument()
    expect(last).toHaveAttribute('aria-hidden', 'true')
    expect(last?.querySelector('.resolution-trace-status')).toHaveTextContent('')
    expect(screen.queryAllByText('Completed')).toHaveLength(0)

    for (let tick = 0; tick < 4; tick += 1) act(() => vi.advanceTimersByTime(1100))
    expect(container.querySelector('[data-step-id="answer"]')).toHaveAttribute('data-reached', 'true')
    expect(screen.getByText('NOT_EVALUATED')).toBeInTheDocument()
    expect(screen.getAllByText('Completed')).toHaveLength(2)
  })

  it('never renders a live step before the application reports it', () => {
    // The Operator desk reads this panel as a record of work that happened.
    render(<ResolutionTrace mode="live" busy steps={[steps[0]]} />)
    expect(screen.getByText('Read catalog')).toBeInTheDocument()
    expect(screen.queryByText('Save answer')).not.toBeInTheDocument()
    expect(screen.queryByText('Observe policy boundary')).not.toBeInTheDocument()
  })

  it('does not confuse a missing policy decision or a build block with a permit or denial', () => {
    expect(traceStatus('not_enforced')).toBe('unknown')
    expect(traceStatus('NOT_EVALUATED')).toBe('unknown')
    expect(traceStatus('policy_denied')).toBe('denied')
    expect(traceStatus('blocked')).toBe('blocked')
    expect(traceStatus('unavailable')).toBe('unavailable')
  })
})
