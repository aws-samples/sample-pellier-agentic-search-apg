/**
 * ConciergeCapabilityState — one state per distinct cause, never a
 * contradictory fallthrough.
 *
 * Regression coverage for `config_unavailable`: capabilities and config
 * are fetched in parallel in `useOperatorConcierge`, so capabilities can
 * load successfully even when config fails. Before this branch existed,
 * that combination fell through to the "ready"/"read-only" render below
 * using whatever capabilities did arrive, while `OperatorConcierge.tsx`
 * simultaneously rendered a lower recovery banner reading "The
 * investigation service configuration could not be read." for the exact
 * same status -- the same pane disagreeing with itself about whether
 * anything was wrong.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ConciergeCapabilityState from './ConciergeCapabilityState'
import type { CapabilitySnapshot } from '../../services/operator'

const READY_CAPABILITIES: CapabilitySnapshot = {
  capabilities: {
    initiate_return: { state: 'available', reason: 'Governance verified.' },
    escalate_to_human: { state: 'available', reason: 'Governance verified.' },
    issue_credit: { state: 'available', reason: 'Governance verified.' },
  },
  observedAt: '2026-09-19T00:00:00Z',
  source: 'agentcore',
  ttlSeconds: 60,
  governedActionsAvailable: true,
  cached: false,
}

describe('ConciergeCapabilityState', () => {
  it('renders a distinct configuration-unavailable state, not the ready state', () => {
    render(
      <ConciergeCapabilityState
        status="config_unavailable"
        capabilities={READY_CAPABILITIES}
        config={null}
      />,
    )

    expect(
      screen.getByText('The investigation service configuration could not be read.'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('operator-concierge-state')).toHaveAttribute(
      'data-state',
      'conversation',
    )
    // Must not also claim readiness -- the exact contradiction this fixes.
    expect(screen.queryByText(/^Ready$/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('operator-concierge-capabilities')).not.toBeInTheDocument()
  })

  it('renders the ready state when nothing failed', () => {
    render(
      <ConciergeCapabilityState
        status="ready"
        capabilities={READY_CAPABILITIES}
        config={null}
      />,
    )

    expect(
      screen.queryByText('The investigation service configuration could not be read.'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('operator-concierge-state')).toHaveAttribute(
      'data-state',
      'ready',
    )
  })
})
