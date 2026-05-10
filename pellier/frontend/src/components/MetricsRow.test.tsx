/**
 * MetricsRow tests — four real metric cards above the chat/tabs split.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import MetricsRow from './MetricsRow'

describe('MetricsRow', () => {
  it('renders all four metric cards with their labels', () => {
    render(
      <MetricsRow
        skillCount={2}
        elapsedMs={14163}
        toolsUsed={5}
        confidencePercent={94}
      />,
    )
    expect(screen.getByTestId('metric-card-skills')).toBeInTheDocument()
    expect(screen.getByTestId('metric-card-elapsed')).toBeInTheDocument()
    expect(screen.getByTestId('metric-card-tools-used')).toBeInTheDocument()
    expect(screen.getByTestId('metric-card-confidence')).toBeInTheDocument()
  })

  it('renders real values when supplied', () => {
    render(
      <MetricsRow
        skillCount={2}
        elapsedMs={14163}
        toolsUsed={5}
        confidencePercent={94}
      />,
    )
    expect(screen.getByTestId('metric-card-skills').textContent).toContain('2')
    expect(screen.getByTestId('metric-card-elapsed').textContent).toContain(
      '14163',
    )
    expect(screen.getByTestId('metric-card-elapsed').textContent).toContain(
      'ms',
    )
    expect(screen.getByTestId('metric-card-tools-used').textContent).toContain(
      '5',
    )
    expect(screen.getByTestId('metric-card-confidence').textContent).toContain(
      '94',
    )
    expect(screen.getByTestId('metric-card-confidence').textContent).toContain(
      '%',
    )
  })

  it('shows em-dash on ELAPSED and CONFIDENCE in the pre-turn empty state', () => {
    render(
      <MetricsRow
        skillCount={0}
        elapsedMs={null}
        toolsUsed={0}
        confidencePercent={null}
      />,
    )
    expect(screen.getByTestId('metric-card-elapsed').textContent).toContain(
      '—',
    )
    expect(screen.getByTestId('metric-card-confidence').textContent).toContain(
      '—',
    )
    // ELAPSED/CONFIDENCE must not render a unit suffix when value is null.
    expect(screen.getByTestId('metric-card-elapsed').textContent).not.toContain(
      'ms',
    )
    expect(
      screen.getByTestId('metric-card-confidence').textContent,
    ).not.toContain('%')
  })

  it('SKILLS and TOOLS USED render 0 (not em-dash) in empty state — 0 is honest', () => {
    render(
      <MetricsRow
        skillCount={0}
        elapsedMs={null}
        toolsUsed={0}
        confidencePercent={null}
      />,
    )
    expect(screen.getByTestId('metric-card-skills').textContent).toContain('0')
    expect(screen.getByTestId('metric-card-tools-used').textContent).toContain(
      '0',
    )
  })
})
