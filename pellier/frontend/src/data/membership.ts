/**
 * The Pellier membership ladder.
 *
 * Three rungs, shown as Member, Silver and Gold and stored authoritatively on `pellier.customers.membership` by
 * scripts/migrations/018_client_book.sql. This module owns the shopper-facing
 * label and the one line of copy that explains what a rung earns, so that copy
 * lives in exactly one place instead of being retyped per surface.
 *
 * Deliberately named `membership`, not `tier`: `product_catalog.tier` already
 * means editorial rank 1/2/3, and the Gateway already uses TIER_* for tool
 * capability. A third meaning of that word would be a landmine.
 *
 * This is presentation only. Membership is an authorization input, and the
 * value a policy decision reads comes from Aurora, never from here.
 *
 * A rung is BUSINESS CONTEXT, never authorization. Gold may qualify a client
 * for an expedited replacement or a larger courtesy allowance, but AgentCore
 * Policy still decides whether the requested action is permitted and Aurora RLS
 * still decides whether the data may be touched. Three independent questions:
 *
 *   tier   what the house offers this client
 *   Cedar  whether the principal may attempt the action
 *   RLS    whether the database will let it through
 */

export const MEMBERSHIP_RUNGS = ['registered', 'circle', 'maison'] as const

export type Membership = (typeof MEMBERSHIP_RUNGS)[number]

interface MembershipDetail {
  /** Shopper-facing label. */
  label: string
  /**
   * A plain functional reading of the rung, shown wherever the tier matters
   * operationally. The label is the brand; this is the comprehension. An
   * advisor who has never seen the ladder still knows what "private client"
   * means.
   */
  descriptor: string
  /** What the rung earns, in Pellier's register. One clause, no exclamation. */
  earns: string
  /** Ascending rank, for comparisons. Never shown. */
  rank: number
}

export const MEMBERSHIP: Record<Membership, MembershipDetail> = {
  registered: {
    label: 'Member',
    descriptor: 'standard client',
    earns: 'Order history and saved sizes',
    rank: 0,
  },
  circle: {
    label: 'Silver',
    descriptor: 'priority client',
    earns: 'Early access and free returns',
    rank: 1,
  },
  maison: {
    label: 'Gold',
    descriptor: 'private client',
    earns: 'Private appointments, repairs, and a dedicated advisor',
    rank: 2,
  },
}

/** Narrow an unknown value to a rung, defaulting to the lowest. */
export function toMembership(value: unknown): Membership {
  return MEMBERSHIP_RUNGS.includes(value as Membership)
    ? (value as Membership)
    : 'registered'
}

export function membershipLabel(value: unknown): string {
  return MEMBERSHIP[toMembership(value)].label
}
