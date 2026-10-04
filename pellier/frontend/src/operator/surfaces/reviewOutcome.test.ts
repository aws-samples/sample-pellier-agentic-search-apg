import { describe, expect, it } from 'vitest'
import { outcomeKind, outcomeLine } from './ReviewQueue'
import type { OperatorReview } from '../../services/operator'

function review(overrides: Partial<OperatorReview> = {}): OperatorReview {
  return {
    reviewId: 1,
    customerId: 'CUST-THEO',
    customerName: 'Theo',
    slug: 'theo',
    personaId: 'theo',
    action: 'give_store_credit',
    parameters: {},
    status: 'pending',
    humanState: 'confirmation_required',
    assurance: {
      human: 'CONFIRMATION_REQUIRED',
      policy: 'PENDING',
      aurora: 'NOT_EVALUATED',
      evidence: 'PENDING',
    },
    sourceTurnId: null,
    execution: null,
    ...overrides,
  } as OperatorReview
}

describe('outcomeKind', () => {
  it('keeps a proposal pending until a person decides', () => {
    expect(outcomeKind(review())).toBe('pending')
  })

  it('tells a policy refusal apart from a carried-out write', () => {
    const confirmed = {
      humanState: 'confirmed' as const,
      execution: { startedAt: '2026-09-03T00:00:00Z' } as unknown as OperatorReview['execution'],
    }
    expect(
      outcomeKind(
        review({
          ...confirmed,
          assurance: { human: 'CONFIRMED', policy: 'DENY', aurora: 'NOT_REACHED', evidence: 'POLICY_PROOF' },
        } as Partial<OperatorReview>),
      ),
    ).toBe('refused')
    expect(
      outcomeKind(
        review({
          ...confirmed,
          assurance: { human: 'CONFIRMED', policy: 'ALLOW', aurora: 'PERMITTED', evidence: 'RECEIPTED' },
        } as Partial<OperatorReview>),
      ),
    ).toBe('executed')
    expect(
      outcomeKind(
        review({
          ...confirmed,
          assurance: { human: 'CONFIRMED', policy: 'ALLOW', aurora: 'DENIED', evidence: 'RECEIPTED' },
        } as Partial<OperatorReview>),
      ),
    ).toBe('refused')
  })

  it('marks a confirmed but unexecuted review as approved', () => {
    expect(outcomeKind(review({ humanState: 'confirmed', execution: null }))).toBe('approved')
    expect(outcomeKind(review({ humanState: 'declined' }))).toBe('declined')
  })
})

describe('a refused governed rail', () => {
  const refusedAxes = {
    human: 'CONFIRMED',
    policy: 'EVALUATION_INCOMPLETE',
    aurora: 'NOT_REACHED',
    evidence: 'NO_EXECUTION',
  } as OperatorReview['assurance']

  it('is neither a policy refusal nor an unverified outcome', () => {
    const refused = review({
      humanState: 'confirmed',
      assurance: refusedAxes,
      execution: { rail: 'refused', startedAt: '2026-09-03T00:00:00Z' } as unknown as OperatorReview['execution'],
    } as Partial<OperatorReview>)
    expect(outcomeKind(refused)).toBe('unavailable')
    expect(outcomeLine(refused)).toBe('Store credit not submitted; the governed rail was unavailable')
  })

  it('is recognised from the axes alone when an older receipt carries no rail', () => {
    const refused = review({
      humanState: 'confirmed',
      assurance: refusedAxes,
      execution: { startedAt: '2026-09-03T00:00:00Z' } as unknown as OperatorReview['execution'],
    } as Partial<OperatorReview>)
    expect(outcomeKind(refused)).toBe('unavailable')
  })
})
