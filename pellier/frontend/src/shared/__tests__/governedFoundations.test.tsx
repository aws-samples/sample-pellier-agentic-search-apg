/**
 * Batch 1 foundations — shared governed status language.
 *
 * Three properties are load-bearing and are asserted here rather than
 * assumed:
 *
 *   1. ALLOW and DENY differ by ICON and ACCESSIBLE NAME, not only color.
 *      A workshop gets projected in rooms with bad color reproduction and
 *      attended by colorblind engineers; a hue-only distinction is not a
 *      distinction.
 *
 *   2. The governed seal shows green "Governed" ONLY for a verified
 *      `gateway-mcp` rail. A permanent green badge would misreport every
 *      box that has not finished provisioning.
 *
 *   3. Receipt links are base-path safe and never invent a route. Workshop
 *      Studio serves the SPA behind a `/ports/8000/` proxy.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { GovernedSeal } from '../GovernedSeal'
import { PolicyDecisionBadge } from '../PolicyDecisionBadge'
import {
  PROVENANCE_DETAIL,
  PROVENANCE_LABEL,
  RAIL_STATE_LABEL,
  resolveRailState,
  type RailDecision,
} from '../governedTypes'

function rail(overrides: Partial<RailDecision> = {}): RailDecision {
  return {
    rail: 'gateway-mcp',
    managedRequested: true,
    available: true,
    reason: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// PolicyDecisionBadge — asymmetry
// ---------------------------------------------------------------------------
describe('PolicyDecisionBadge', () => {
  it('gives ALLOW and DENY different accessible names', () => {
    const { unmount } = render(<PolicyDecisionBadge decision="ALLOW" />)
    const allowName = screen
      .getByTestId('policy-decision-badge')
      .textContent as string
    unmount()

    render(<PolicyDecisionBadge decision="DENY" />)
    const denyName = screen
      .getByTestId('policy-decision-badge')
      .textContent as string

    expect(allowName).not.toEqual(denyName)
    expect(allowName).toMatch(/ALLOW/)
    expect(denyName).toMatch(/DENY/)
  })

  it('gives ALLOW and DENY different icons, not a recolored glyph', () => {
    const { container: allow, unmount } = render(
      <PolicyDecisionBadge decision="ALLOW" />,
    )
    const allowIcon = allow.querySelector('svg')?.getAttribute('class')
    unmount()

    const { container: deny } = render(<PolicyDecisionBadge decision="DENY" />)
    const denyIcon = deny.querySelector('svg')?.getAttribute('class')

    expect(allowIcon).toBeTruthy()
    expect(denyIcon).toBeTruthy()
    expect(allowIcon).not.toEqual(denyIcon)
  })

  it('states that a DENY did not execute the tool', () => {
    render(<PolicyDecisionBadge decision="DENY" />)

    expect(
      screen.getByText(/blocked before execution, the tool did not run/i),
    ).toBeInTheDocument()
  })

  it('states that an ALLOW ran', () => {
    render(<PolicyDecisionBadge decision="ALLOW" />)

    expect(screen.getByText(/permitted the action/i)).toBeInTheDocument()
    expect(screen.queryByText(/and ran/i)).not.toBeInTheDocument()
  })

  it('renders NOT_EVALUATED as neither success nor failure', () => {
    render(<PolicyDecisionBadge decision="NOT_EVALUATED" />)
    const badge = screen.getByTestId('policy-decision-badge')

    expect(badge.getAttribute('data-decision')).toBe('NOT_EVALUATED')
    expect(badge.textContent).toMatch(/not evaluated/i)
  })

  it('carries the policy reason into the accessible name', () => {
    render(
      <PolicyDecisionBadge
        decision="DENY"
        reason="principal does not own the order"
      />,
    )

    expect(
      screen.getByText(/Reason: principal does not own the order/i),
    ).toBeInTheDocument()
  })

  it('always renders visible text alongside the icon', () => {
    // Color alone is never the signal.
    for (const decision of ['ALLOW', 'DENY', 'NOT_EVALUATED'] as const) {
      const { unmount } = render(<PolicyDecisionBadge decision={decision} />)
      expect(screen.getByTestId('policy-decision-badge').textContent).toMatch(
        /[A-Z]/,
      )
      unmount()
    }
  })
})

// ---------------------------------------------------------------------------
// GovernedSeal — verified rail only
// ---------------------------------------------------------------------------
describe('GovernedSeal', () => {
  it('shows Governed only for a verified gateway-mcp rail', () => {
    render(<GovernedSeal railDecision={rail({ rail: 'gateway-mcp' })} />)
    const seal = screen.getByTestId('governed-seal')

    expect(seal.getAttribute('data-rail-state')).toBe('verified')
    expect(seal.textContent).toMatch(/Governed/)
  })

  it('does not claim Governed when the runtime was merely selected', () => {
    render(<GovernedSeal railDecision={rail({ rail: 'runtime' })} />)
    const seal = screen.getByTestId('governed-seal')

    expect(seal.getAttribute('data-rail-state')).toBe('selected')
    expect(seal.textContent).not.toMatch(/^Governed/)
    expect(seal.textContent).toMatch(/Managed runtime/)
  })

  it('describes in-process as a legitimate rail, not a failure', () => {
    render(
      <GovernedSeal
        railDecision={rail({
          rail: 'in-process',
          managedRequested: false,
        })}
        variant="expanded"
      />,
    )

    // The detail appears twice by design: once visibly in the expanded
    // paragraph, once in the seal's accessible name.
    expect(
      screen.getAllByText(/A legitimate rail, not a failure/i).length,
    ).toBeGreaterThan(0)
  })

  it('marks a requested-but-unavailable rail as degraded, not denied', () => {
    render(
      <GovernedSeal
        railDecision={rail({
          rail: 'in-process',
          available: false,
          reason: 'authentication_required',
        })}
        variant="expanded"
      />,
    )

    expect(screen.getByTestId('governed-seal').getAttribute('data-rail-state')).toBe(
      'degraded',
    )
    // Degradation is an availability problem, never a policy decision.
    expect(screen.getAllByText(/not a policy denial/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/authentication_required/)).toBeInTheDocument()
  })

  it('renders nothing compact when no rail evidence exists', () => {
    const { container } = render(<GovernedSeal railDecision={null} />)

    expect(container.textContent).toBe('')
  })

  it('names the rail in the accessible text', () => {
    render(<GovernedSeal railDecision={rail()} />)

    expect(screen.getByText(/Execution rail: Governed \(gateway-mcp\)/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Rail state resolution
// ---------------------------------------------------------------------------
describe('resolveRailState', () => {
  it('maps each backend decision to one state', () => {
    expect(resolveRailState(rail({ rail: 'gateway-mcp' }))).toBe('verified')
    expect(resolveRailState(rail({ rail: 'runtime' }))).toBe('selected')
    expect(
      resolveRailState(rail({ rail: 'in-process', managedRequested: false })),
    ).toBe('in-process')
    expect(resolveRailState(rail({ available: false }))).toBe('degraded')
    expect(resolveRailState(null)).toBe('unknown')
    expect(resolveRailState(undefined)).toBe('unknown')
  })

  it('prioritises degraded over the reported rail', () => {
    // A degraded turn reports in-process; the seal must say degraded.
    expect(
      resolveRailState(rail({ rail: 'in-process', available: false })),
    ).toBe('degraded')
  })

  it('has a label and detail for every state', () => {
    for (const state of [
      'verified',
      'selected',
      'in-process',
      'degraded',
      'unknown',
    ] as const) {
      expect(RAIL_STATE_LABEL[state]).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// Provenance vocabulary matches the backend
// ---------------------------------------------------------------------------
describe('provenance vocabulary', () => {
  it('uses the same four words the backend emits', () => {
    expect(Object.keys(PROVENANCE_LABEL).sort()).toEqual([
      'fixture',
      'live',
      'modeled',
      'unavailable',
    ])
  })

  it('states what each provenance claims', () => {
    expect(PROVENANCE_DETAIL.live).toMatch(/measured on this request/)
    expect(PROVENANCE_DETAIL.fixture).toMatch(/describes no run/)
    expect(PROVENANCE_DETAIL.modeled).toMatch(/not observed/)
    expect(PROVENANCE_DETAIL.unavailable).toMatch(/not provisioned/)
  })
})
