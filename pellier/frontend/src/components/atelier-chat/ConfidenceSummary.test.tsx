/**
 * ConfidenceSummary tests — green confidence band at the end of a turn.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ConfidenceSummary from './ConfidenceSummary'
import type { WorkshopPanelEvent } from '../../services/workshop'

function confidencePanel(
  resultCell: string,
  meta: string,
): WorkshopPanelEvent {
  return {
    type: 'panel',
    agent: 'confidence',
    tag: 'MEMORY · CONFIDENCE',
    tag_class: 'green',
    title: 'Confidence from data coverage',
    sql: '',
    columns: ['signal', 'contribution'],
    rows: [
      ['picks survived fact-check', '3 → +20'],
      ['base', '60'],
      ['sum', '94'],
      ['result', resultCell],
    ],
    meta,
    duration_ms: 1,
    ts_ms: 0,
  }
}

describe('ConfidenceSummary', () => {
  it('renders the percent extracted from the result row', () => {
    render(
      <ConfidenceSummary
        panel={confidencePanel('94 (clamped to [30, 98])', 'deterministic')}
      />,
    )
    expect(screen.getByText('94%')).toBeInTheDocument()
  })

  it('renders the italic justification from the panel meta', () => {
    render(
      <ConfidenceSummary
        panel={confidencePanel(
          '85',
          'based on 3 prior orders · 2 picks survived fact-check',
        )}
      />,
    )
    expect(
      screen.getByText(/based on 3 prior orders/),
    ).toBeInTheDocument()
  })

  it('returns null when no panel is supplied (pre-turn empty state)', () => {
    const { container } = render(<ConfidenceSummary panel={undefined} />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null when the result row is missing', () => {
    const panel = confidencePanel('', 'x')
    panel.rows = panel.rows.filter((r) => r[0] !== 'result')
    const { container } = render(<ConfidenceSummary panel={panel} />)
    expect(container.firstChild).toBeNull()
  })

  it("strips HTML from the panel meta so backend inline <span>s don't leak", () => {
    render(
      <ConfidenceSummary
        panel={confidencePanel(
          '77',
          'deterministic · <span style="color:red">no LLM</span>',
        )}
      />,
    )
    const el = screen.getByTestId('confidence-summary')
    expect(el.textContent).not.toContain('<span')
    expect(el.textContent).toContain('no LLM')
  })
})
