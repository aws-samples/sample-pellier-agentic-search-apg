/**
 * Contextual templates. Shortcuts into the same orchestrator, never canned answers.
 *
 * A template contributes structured intent and a request sentence. It does not have
 * its own endpoint, its own response shape, or its own prose — selecting
 * "Summarize client" and typing the equivalent question must produce the same code
 * path, or the surface is demonstrating something the product cannot do.
 *
 * Visibility is deterministic and doubly gated. A suggestion appears because loaded
 * client state satisfies its requirement — not because a model proposed it; asking
 * Bedrock why a suggestion exists would make the empty state itself a synthesis — AND
 * because the server publishes the workflow it advertises.
 *
 * That second gate is the load-bearing one. `replacement_search` shipped as a visible
 * row while its request classified to `client_summary`, so the surface offered one
 * workflow and ran another. A template now names its workflow kind explicitly and is
 * filtered against `supportedWorkflowKinds`, which makes the failure structural rather
 * than a thing to remember: an unimplemented workflow cannot be offered.
 */

import type { OperatorClientRecord } from '../../services/operator'
import { WORKSHOP_JOURNEYS } from '../../data/workshopJourneys'

export type TemplateId =
  | 'summarize_client'
  | 'draft_client_note'
  | 'investigate_resolution'
  | 'replacement_search'

export interface TemplateContext {
  clientName: string
  firstName: string
  orderCount: number
  openTicketCount: number
  /** A ticket asserting a return with no authoritative row behind it. */
  unconfirmedReturnAssertion: boolean
  ticketId: string
  ticketSubject: string
  recentOrderId: number | null
  recentProductName: string
}

export interface ConciergeTemplate {
  id: TemplateId
  /**
   * The workflow kind this row advertises, matching a key in the backend's
   * `WORKFLOWS` registry. Not derived from `id`: the ids read as UI labels
   * (`summarize_client`) and the kinds as orchestrator contracts
   * (`client_summary`), and quietly conflating them is how a rename drifts.
   */
  workflow: string
  /** Eyebrow above the row. Categorises, never decorates. */
  group: string
  label: string
  /** One line saying why this is offered, from real context. */
  description: (ctx: TemplateContext) => string
  /** All four are reads in Phase 4B. */
  classification: 'read'
  /** Whether loaded context supports offering it at all. */
  isAvailable: (ctx: TemplateContext) => boolean
  /** Higher sorts first. Derived from context, not from a model. */
  rank: (ctx: TemplateContext) => number
  buildRequest: (ctx: TemplateContext) => string
}

export const GUIDED_SERVICE_RECOVERY_PROMPTS =
  WORKSHOP_JOURNEYS.jessica.prompts

export const TEMPLATES: ConciergeTemplate[] = [
  {
    id: 'investigate_resolution',
    workflow: 'investigate_resolution',
    group: 'Service context',
    label: 'Investigate service issue',
    description: (ctx) =>
      ctx.unconfirmedReturnAssertion
        ? `${ctx.ticketId} remains unresolved and its return record is unconfirmed`
        : `${ctx.ticketId} remains unresolved`,
    classification: 'read',
    isAvailable: (ctx) => ctx.openTicketCount > 0,
    // An unresolved ticket whose evidence disagrees with itself is the most useful
    // thing an operator can be pointed at.
    rank: (ctx) => (ctx.unconfirmedReturnAssertion ? 100 : 70),
    buildRequest: (ctx) =>
      `Investigate ${ctx.firstName}'s open service issue (${ctx.ticketId}) and ` +
      `recommend the next fair step. Distinguish what the records establish from ` +
      `what a source reports.`,
  },
  {
    id: 'summarize_client',
    workflow: 'client_summary',
    group: 'Overview',
    label: 'Summarize client',
    description: (ctx) =>
      `Review ${ctx.orderCount} orders and current service context`,
    classification: 'read',
    isAvailable: (ctx) => ctx.orderCount > 0,
    rank: () => 60,
    buildRequest: (ctx) =>
      `Summarize ${ctx.firstName}'s recent relationship with Pellier. Focus on ` +
      `purchases, service history, and anything I should know before responding.`,
  },
  {
    id: 'draft_client_note',
    workflow: 'draft_client_note',
    group: 'Draft',
    label: 'Draft a client note',
    description: () => 'Write from verified recent activity',
    classification: 'read',
    isAvailable: (ctx) => ctx.orderCount > 0,
    rank: () => 40,
    buildRequest: (ctx) =>
      `Draft a short, sincere note to ${ctx.firstName} that references their recent ` +
      `activity. Keep it warm but restrained.`,
  },
  {
    id: 'replacement_search',
    workflow: 'replacement_search',
    group: 'Catalog',
    label: 'Find a replacement',
    // Never "in-stock alternatives" in the label. Ledger coverage exists for 40 of
    // 100 catalog products, so promising availability before the workflow has
    // established it would be a claim the result often cannot honour. The row names
    // the real item and the real order; availability is reported per option, after.
    description: (ctx) =>
      ctx.recentProductName
        ? `Compare replacement options for ${ctx.recentProductName} · order #${ctx.recentOrderId}`
        : 'Compare replacement options',
    classification: 'read',
    // Only when an order AND a product can actually be resolved. Offering it
    // without a resolvable item would be a dead end dressed as a capability.
    isAvailable: (ctx) => Boolean(ctx.recentOrderId && ctx.recentProductName),
    rank: () => 20,
    // No "upgrade": no catalog attribute establishes one, so asking for it invites
    // the model to invent the claim the backend refuses to make.
    buildRequest: (ctx) =>
      `For order #${ctx.recentOrderId}, find a replacement for ` +
      `"${ctx.recentProductName}".`,
  },
]

/** Context from loaded record state. No inference, no model. */
export function buildTemplateContext(
  record: OperatorClientRecord | null,
): TemplateContext | null {
  if (!record) return null
  const client = record.client
  const orders = record.orders ?? []
  const tickets = record.tickets ?? []
  const evidence = (client as unknown as {
    returnEvidence?: { unconfirmedReturnAssertion?: boolean }
  }).returnEvidence
  const first = client.name.trim().split(/\s+/)[0] || client.name
  const newest = orders[0]
  const currentTicket = tickets.find((ticket) => ticket.status === 'open' || ticket.status === 'pending')
  return {
    clientName: client.name,
    firstName: first,
    orderCount: orders.length,
    openTicketCount: tickets.filter((t) =>
      t.status === 'open' || t.status === 'pending',
    ).length,
    unconfirmedReturnAssertion: Boolean(evidence?.unconfirmedReturnAssertion),
    ticketId: currentTicket?.ticketId ?? '',
    ticketSubject: currentTicket?.subject ?? '',
    recentOrderId: newest?.orderId ?? null,
    recentProductName: newest?.productName ?? '',
  }
}

/**
 * The templates worth offering, best first.
 *
 * `supported` is the server's published workflow list. Omitting it offers nothing:
 * a caller that has not yet read which workflows exist cannot know that any of these
 * would run, and defaulting to "show everything" is what produced a Replacement Search
 * row that executed a client summary.
 */
export function rankTemplates(
  ctx: TemplateContext | null,
  supported: string[] | undefined,
): ConciergeTemplate[] {
  if (!ctx || !supported || supported.length === 0) return []
  const published = new Set(supported)
  return TEMPLATES.filter(
    (t) => published.has(t.workflow) && t.isAvailable(ctx),
  ).sort((a, b) => b.rank(ctx) - a.rank(ctx))
}
