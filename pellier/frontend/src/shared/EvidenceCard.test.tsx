/**
 * EvidenceCard contract.
 *
 * One radius replaced six, so the radius is asserted. `quiet` exists to make
 * an empty panel stop pretending it has content, so the absence of the shadow
 * is asserted. And no variant may add a hover lift: lift is an affordance, and
 * these cards are not pressable.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EvidenceCard } from './EvidenceCard'

describe('EvidenceCard', () => {
  it('is one radius, one hairline, one warm resting shadow', () => {
    render(<EvidenceCard data-testid="card">Receipt</EvidenceCard>)

    expect(screen.getByTestId('card')).toHaveStyle({
      borderRadius: 'var(--gov-radius-lg)',
      border: '1px solid var(--shared-rule-1)',
      background: 'var(--shared-panel)',
      boxShadow: 'var(--gov-shadow-card)',
      padding: '24px',
    })
  })

  it('does not tint its shadow cool', () => {
    // The card shadow used to be rgb(20 28 24), a green-grey left over from
    // an earlier cool-canvas period. On warm paper it read as a smudge.
    render(<EvidenceCard data-testid="card">Receipt</EvidenceCard>)
    const style = screen.getByTestId('card').getAttribute('style') ?? ''
    expect(style).not.toMatch(/20 28 24/)
  })

  it('drops the shadow and recedes when quiet', () => {
    render(
      <EvidenceCard quiet data-testid="card">
        Not recorded
      </EvidenceCard>,
    )
    const card = screen.getByTestId('card')
    expect(card).toHaveAttribute('data-quiet', 'true')
    expect(card).toHaveStyle({
      boxShadow: 'none',
      background: 'var(--shared-panel-muted)',
    })
  })

  it('takes 20px padding in a dense row', () => {
    render(
      <EvidenceCard padding="compact" data-testid="card">
        Receipt
      </EvidenceCard>,
    )
    expect(screen.getByTestId('card')).toHaveStyle({ padding: '20px' })
  })

  it('publishes its tone as a custom property the tick reads', () => {
    render(
      <EvidenceCard tone="degraded" data-testid="card">
        Degraded
      </EvidenceCard>,
    )
    const card = screen.getByTestId('card')
    expect(card).toHaveAttribute('data-tone', 'degraded')
    expect(card.style.getPropertyValue('--gov-card-tone')).toBe(
      'var(--shared-status-degraded-fg, var(--dl-warn))',
    )
  })

  it('leaves a neutral card with no tick colour to draw', () => {
    render(<EvidenceCard data-testid="card">Receipt</EvidenceCard>)
    const card = screen.getByTestId('card')
    expect(card).toHaveAttribute('data-tone', 'neutral')
    expect(card.style.getPropertyValue('--gov-card-tone')).toBe('transparent')
  })

  it('never adds a lift, because it is not pressable', () => {
    render(
      <EvidenceCard tone="brand" data-testid="card">
        Receipt
      </EvidenceCard>,
    )
    const style = screen.getByTestId('card').getAttribute('style') ?? ''
    expect(style).not.toMatch(/translate|transform/)
  })

  it('renders as the element the evidence actually is', () => {
    render(
      <EvidenceCard as="section" aria-label="Write receipt" data-testid="card">
        Receipt
      </EvidenceCard>,
    )
    const card = screen.getByTestId('card')
    expect(card.tagName).toBe('SECTION')
    expect(card).toHaveAttribute('aria-label', 'Write receipt')
  })

  it('keeps the class hook the stylesheet needs alongside a caller class', () => {
    render(
      <EvidenceCard className="custom-class" data-testid="card">
        Receipt
      </EvidenceCard>,
    )
    const card = screen.getByTestId('card')
    expect(card).toHaveClass('gov-evidence-card')
    expect(card).toHaveClass('custom-class')
  })
})
