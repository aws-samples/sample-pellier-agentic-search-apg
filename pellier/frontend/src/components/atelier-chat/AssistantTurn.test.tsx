/**
 * AssistantTurn tests — composition of plan chip + tool chips +
 * assistant text for a single Turn.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import AssistantTurn from './AssistantTurn'
import type {
  Turn,
  WorkshopPanelEvent,
  WorkshopPlanEvent,
} from '../../services/workshop'

function plan(): WorkshopPlanEvent {
  return {
    type: 'plan',
    title: 'Decomposed into 5 steps',
    steps: ['Parse intent', 'Pull memory', 'Search catalog', 'Filter', 'Synthesize'],
    duration_ms: 45,
    ts_ms: 0,
  }
}

function panel(overrides: Partial<WorkshopPanelEvent> = {}): WorkshopPanelEvent {
  return {
    type: 'panel',
    agent: 'search',
    tag: 'TOOL · SEARCH',
    tag_class: 'cyan',
    title: 'Searched catalog',
    sql: '',
    columns: ['name'],
    rows: [['Linen Shirt'], ['Camp Shirt']],
    meta: '',
    duration_ms: 142,
    ts_ms: 100,
    ...overrides,
  }
}

function turn(overrides: Partial<Turn> = {}): Turn {
  return {
    id: 't1',
    user_text: 'find me linen shirts',
    assistant_text: 'Three pieces stand out, all under $150.',
    plan: plan(),
    panels: [panel()],
    ...overrides,
  }
}

describe('AssistantTurn — composition', () => {
  it('renders plan chip, tool chip, and assistant text in order', () => {
    render(<AssistantTurn turn={turn()} />)
    expect(screen.getByTestId('plan-preview-chip')).toBeInTheDocument()
    expect(screen.getByTestId('tool-chip-TOOL · SEARCH')).toBeInTheDocument()
    expect(screen.getByTestId('assistant-text')).toBeInTheDocument()
  })

  it('omits the plan chip when no plan is on the turn', () => {
    render(<AssistantTurn turn={turn({ plan: undefined })} />)
    expect(screen.queryByTestId('plan-preview-chip')).not.toBeInTheDocument()
  })

  it("does not render AssistantText when assistant_text is null (in-flight turn)", () => {
    render(<AssistantTurn turn={turn({ assistant_text: null })} />)
    expect(screen.queryByTestId('assistant-text')).not.toBeInTheDocument()
  })

  it('uses the TOOL_LABEL override for known tool tags', () => {
    render(<AssistantTurn turn={turn()} />)
    expect(screen.getByText('Searched product catalog')).toBeInTheDocument()
  })

  it('falls back to the panel title for unknown tool tags', () => {
    const unknown = panel({
      tag: 'TOOL · SOMETHING_NEW',
      title: 'Did the new thing',
    })
    render(<AssistantTurn turn={turn({ panels: [unknown] })} />)
    expect(screen.getByText('Did the new thing')).toBeInTheDocument()
  })
})

describe('AssistantTurn — citation wiring', () => {
  it('fires onOpenTrace("plan") when the plan chip view-trace link is clicked', async () => {
    const onOpenTrace = vi.fn()
    const user = userEvent.setup()
    render(<AssistantTurn turn={turn()} onOpenTrace={onOpenTrace} />)
    await user.click(screen.getByTestId('plan-preview-view-trace'))
    expect(onOpenTrace).toHaveBeenCalledWith('plan')
  })

  it('fires onOpenTrace(panel.tag) when a tool chip "Open in trace" is clicked', async () => {
    const onOpenTrace = vi.fn()
    const user = userEvent.setup()
    render(<AssistantTurn turn={turn()} onOpenTrace={onOpenTrace} />)
    // Expand the chip first so the inner action is visible.
    await user.click(screen.getByText('Searched product catalog'))
    await user.click(screen.getByTestId('tool-chip-open-trace-TOOL · SEARCH'))
    expect(onOpenTrace).toHaveBeenCalledWith('TOOL · SEARCH')
  })

  it('fires onOpenTrace with the citation ref when a citation pill is clicked', async () => {
    const onOpenTrace = vi.fn()
    const user = userEvent.setup()
    render(
      <AssistantTurn
        turn={turn({
          citations: [{ k: 'beans.b_x', ref: 'trace 7' }],
        })}
        onOpenTrace={onOpenTrace}
      />,
    )
    await user.click(screen.getByTestId('citation-pill-trace 7'))
    expect(onOpenTrace).toHaveBeenCalledWith('trace 7')
  })
})
