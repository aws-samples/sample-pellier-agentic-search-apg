/**
 * ToolChip tests — collapsed / expanded tool-call card.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import ToolChip from './ToolChip'
import type { WorkshopPanelEvent } from '../../services/workshop'

function panel(overrides: Partial<WorkshopPanelEvent> = {}): WorkshopPanelEvent {
  return {
    type: 'panel',
    agent: 'search',
    tag: 'TOOL REGISTRY · DISCOVER',
    tag_class: 'cyan',
    title: 'Ranked tools by semantic match',
    sql: 'SELECT name FROM tools LIMIT 4',
    columns: ['tool', 'score'],
    rows: [
      ['check_inventory', '0.55'],
      ['get_customer_history', '0.52'],
    ],
    meta: 'one pgvector query',
    duration_ms: 142,
    ts_ms: 0,
    ...overrides,
  }
}

describe('ToolChip — collapsed state', () => {
  it('renders the tool label and duration when collapsed', () => {
    render(<ToolChip panel={panel()} actionLabel="Searched product catalog" />)
    expect(
      screen.getByText('Searched product catalog'),
    ).toBeInTheDocument()
    expect(screen.getByText('142ms')).toBeInTheDocument()
  })

  it('shows the N-results summary template by default', () => {
    render(<ToolChip panel={panel({ rows: [['x', 'y'], ['a', 'b'], ['c', 'd']] })} />)
    expect(screen.getByText('— 3 results')).toBeInTheDocument()
  })

  it('singularizes the result count at 1', () => {
    render(<ToolChip panel={panel({ rows: [['only-one', '1.0']] })} />)
    expect(screen.getByText('— 1 result')).toBeInTheDocument()
  })

  it('falls back to meta text when there are no rows', () => {
    render(
      <ToolChip
        panel={panel({
          rows: [],
          columns: [],
          meta: 'policy retrieved from support table',
        })}
      />,
    )
    expect(
      screen.getByText(/— policy retrieved from support table/),
    ).toBeInTheDocument()
  })

  it('does not render the expanded body while collapsed', () => {
    render(<ToolChip panel={panel()} />)
    const chip = screen.getByTestId('tool-chip-TOOL REGISTRY · DISCOVER')
    expect(chip.getAttribute('data-expanded')).toBe('false')
  })
})

describe('ToolChip — expanded state', () => {
  it('toggles expansion on header click', async () => {
    const user = userEvent.setup()
    render(<ToolChip panel={panel()} />)
    const chip = screen.getByTestId('tool-chip-TOOL REGISTRY · DISCOVER')
    expect(chip.getAttribute('data-expanded')).toBe('false')
    await user.click(screen.getAllByRole('button')[0])
    expect(chip.getAttribute('data-expanded')).toBe('true')
  })

  it('renders the first two SQL lines + truncation marker when expanded', () => {
    const longSql =
      'SELECT a, b, c\nFROM tools\nWHERE enabled\nORDER BY score\nLIMIT 5'
    render(<ToolChip panel={panel({ sql: longSql })} defaultExpanded />)
    const chip = screen.getByTestId('tool-chip-TOOL REGISTRY · DISCOVER')
    expect(chip.textContent).toContain('SELECT a, b, c')
    expect(chip.textContent).toContain('···')
  })

  it('fires onOpenTrace when "Open in trace" is clicked', async () => {
    const onOpenTrace = vi.fn()
    const user = userEvent.setup()
    render(
      <ToolChip
        panel={panel()}
        defaultExpanded
        onOpenTrace={onOpenTrace}
      />,
    )
    await user.click(
      screen.getByTestId('tool-chip-open-trace-TOOL REGISTRY · DISCOVER'),
    )
    expect(onOpenTrace).toHaveBeenCalledOnce()
  })
})
