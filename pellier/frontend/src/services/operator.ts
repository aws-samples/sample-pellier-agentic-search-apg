import { apiFetch } from './apiBase'
/**
 * Pellier Operator API client.
 *
 * Every route requires a verified operator-group token, so 401 and 403 are
 * real states the console renders rather than errors to swallow. Every field
 * comes from PostgreSQL/Aurora: there is no committed frontend copy of the
 * client book, because UI state is not evidence.
 */

import type { Membership } from '../data/membership'

import type { CapabilitySnapshot } from './operatorCapabilities'
import type {
  ConciergeConfig,
  ConciergeInvestigationStep,
  ConciergeSession,
  ShopperHandoff,
  ConciergeStreamAnswer,
  ConciergeTurn,
} from './operatorConcierge'

export type { CapabilitySnapshot, Capability, CapabilityState } from './operatorCapabilities'
export type {
  ConciergeConfig,
  ConciergeSession,
  ConciergeMessage,
  ConciergeArtifact,
  ConciergeInvestigationStep,
  ConciergeOrchestration,
  ConciergeStreamAnswer,
  ConciergeEvidenceItem,
  ShopperHandoff,
  ConciergeTurn,
  TurnState,
} from './operatorConcierge'

export interface OperatorClient {
  customerId: string
  /** `CUST-JESSICA` -> `jessica`. Drives the portrait filename. */
  slug: string
  name: string
  membership: Membership
  spend12mo: number
  orderCount: number
  orderValue: number
  lastOrderAt: string | null
  note: string
  /** Set only where a real storefront handoff exists. */
  personaId: string | null
  /**
   * The subject of this client's open service request, when one is open.
   *
   * Distinct from `note`, which is a preferences brief. A card that wants to
   * say what is happening has to read this; deriving it from the brief means
   * parsing prose and presenting the result as a fact.
   */
  openCase?: string | null
  openCaseStatus?: string | null
  /** Present on a single-client read. */
  openTicketCount?: number
  creditBalanceCents?: number
  creditBalance?: string
  returnCount?: number
  returnEvidence?: {
    authoritativeReturnCount: number
    supportAssertsReturn: boolean
    /**
     * True when the ticket asserts a return that no authoritative row backs,
     * scoped to the products the ticket names. Unscoped, any return for the
     * customer flipped this -- including one written by the Lab 4 identity
     * matrix on an unrelated product, which silently emptied the checkpoint.
     */
    unconfirmedReturnAssertion: boolean
    /** The products the open tickets actually name; empty when none match. */
    disputedProductIds?: string[]
  }
}

export interface OperatorOrder {
  orderId: number
  productId: string
  productName: string
  brand: string
  price: number
  quantity: number
  placedAt: string | null
  imageUrl: string
}

export interface OperatorTicket {
  ticketId: string
  subject: string
  status: 'open' | 'pending' | 'resolved' | 'closed'
  channel: string
  lastNote: string
  openedAt: string | null
  resolvedAt: string | null
}

export interface OperatorCredit {
  creditId: number
  amountCents: number
  /** Formatted once by the API so no surface re-derives currency from cents. */
  amount: string
  currency: string
  reason: string
  issuedBy: string | null
  createdAt: string | null
}

export interface OperatorReturn {
  returnId: number
  productId: string
  productName: string
  reason: string
  status: string
  requestedAt: string | null
}

export interface OperatorBook {
  clients: OperatorClient[]
  total: number
  byMembership: Record<Membership, number>
}

export interface OperatorClientRecord {
  /**
   * Which database answered. The record contrasts what a ticket claims with
   * what the authoritative store holds, and that column names the store it
   * read: the same build serves local PostgreSQL in development and Aurora in
   * the workshop.
   */
  dataSource?: string
  client: OperatorClient
  orders: OperatorOrder[]
  tickets: OperatorTicket[]
  credits: OperatorCredit[]
  returns: OperatorReturn[]
}

/**
 * The four assurance axes, exactly as the API resolved them.
 *
 * Independent on purpose. A single boolean would let a human decision imply an
 * authorization decision, which is the confusion this surface exists to
 * dismantle, so the console renders these verbatim and never derives one from
 * another.
 */
export interface ActionAssurance {
  human: 'CONFIRMATION_REQUIRED' | 'CONFIRMED' | 'DECLINED'
  /**
   * ALLOW / DENY / WOULD_DENY come only from a real policy engine response.
   * EVALUATION_INCOMPLETE means the engine was asked and its answer could not
   * be read; POLICY_INFERRED is a text scan of policy source and is not a
   * decision at all.
   */
  policy:
    | 'PENDING'
    | 'NOT_EVALUATED'
    | 'ALLOW'
    | 'DENY'
    | 'WOULD_DENY'
    | 'EVALUATION_INCOMPLETE'
    | 'POLICY_INFERRED'
  aurora:
    | 'NOT_EVALUATED'
    | 'NOT_REACHED'
    | 'PERMITTED'
    | 'DENIED'
    | 'NOT_ENFORCED'
    | 'OUTCOME_UNKNOWN'
  evidence:
    | 'PENDING'
    | 'NO_EXECUTION'
    | 'RECEIPTED'
    | 'POLICY_PROOF'
    | 'ATTEMPT_RECEIPT'
}

/** One governed execution attempt. Each axis comes from its own artifact. */
export interface OperatorExecutionResult {
  reviewId: number
  rail: 'gateway-mcp' | 'in-process' | 'refused'
  executionTurnId: string
  idempotencyKey: string
  /** The operator AgentCore Policy authorizes. */
  actorPrincipal: string
  /** The customer Aurora RLS scopes. Null when the client has no mapping. */
  customerSubject: string | null
  assurance: ActionAssurance
  /** Why each axis is in its state, resolved server-side. */
  notes: Partial<Record<'policy' | 'aurora', string>>
  tool: string
  result: Record<string, unknown>
}

/**
 * A stored execution receipt: what the governance layers decided, and what decided it.
 *
 * This is the artifact migration 021 assumed existed and nothing wrote. Until it
 * shipped, a Cedar DENY left no durable trace anywhere — a denied call correctly writes
 * no `tool_audit` row and claims no idempotency key — so this surface reported
 * `policy: PENDING` for actions Cedar had refused.
 */
export interface OperatorExecutionReceipt {
  receiptId: number
  /**
   * The domain row this execution produced, joined on the write key. Null when the
   * execution wrote nothing — a denial, a refusal, or a non-writing tool.
   *
   * Needed because the client's return history and the return THIS review created live
   * in the same table: without it the record counted its own outcome among the
   * client's "previous damaged returns".
   */
  producedReturnId: number | null
  executionTurnId: string
  tool: string
  /** The Cedar action id evaluated, e.g. `<target>___initiate_return`. */
  gatewayActionId: string
  rail: 'gateway-mcp' | 'in-process' | 'refused'
  /** The operator AgentCore Policy authorized. */
  actorPrincipal: string
  /** The customer Aurora RLS scoped. Null when the client has no mapping. */
  customerSubject: string | null
  policyEngineId: string
  /** ENFORCE or LOG_ONLY at evaluation time. */
  gatewayMode: string
  /**
   * Forbid policies whose statement NAMES this action — not necessarily the one that
   * denied it. The same conditional forbid is listed beside an ALLOW, where it means
   * a rule was evaluated and did not apply.
   */
  matchingForbids: string[]
  idempotencyKey: string
  notes: Partial<Record<'policy' | 'aurora', string>>
  recordedAt: string | null
}

export type ReviewHumanState =
  | 'confirmation_required'
  | 'confirmed'
  | 'declined'

/** Workflow state and references. Never business truth. */
export interface OperatorReview {
  reviewId: number
  customerId: string
  customerName: string
  slug: string
  /** Set only for the three storefront-switchable heroes. */
  personaId: string | null
  action: string
  parameters: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected'
  humanState: ReviewHumanState
  assurance: ActionAssurance
  /** The originating shopper turn. Not shown by default; it is the proof link. */
  sourceTurnId: string | null
  /**
   * Claimed when execution BEGINS. Present with `execution: null` means an attempt
   * started and produced no verdict, which is its own state and not "never tried".
   */
  executionTurnId: string | null
  /**
   * The verdicts of the latest execution attempt, read from
   * `pellier.execution_receipts`, or null when none was attempted.
   *
   * Separate from `assurance` on purpose: the axes are the verdicts, this is what
   * produced them. An ALLOW without `gatewayMode` cannot be told apart from an
   * unenforced observation under LOG_ONLY.
   */
  execution: OperatorExecutionReceipt | null
  orderId: number | null
  /** Current catalog label, resolved from the proposed product on read. */
  productName?: string | null
  issue: string
  recommendation: {
    primaryAction?: string
    rationale?: string
    secondarySuggestion?: {
      action: string
      amountCents?: number
      rationale?: string
    }
  }
  /** Fingerprint of the parameters shown, echoed back on confirm. */
  actionHash: string
  decidedBy: string | null
  /**
   * Who asked, kept apart from the customer the proposal names and from the
   * operator who decides. `unverified` means the requester was not proved to
   * own this customer record. A subject may still identify a signed-in caller.
   */
  requestedBySub: string | null
  requesterKind: 'shopper' | 'operator' | 'unverified'
  requestedAt: string | null
  decidedAt: string | null
}

export function requesterLine(review: Pick<OperatorReview, 'requesterKind' | 'requestedBySub'>): string {
  const subject = review.requestedBySub ? ` (subject ${review.requestedBySub.slice(0, 8)}…)` : ''
  if (review.requesterKind === 'shopper') {
    return `Asked for by the signed-in shopper${subject}.`
  }
  if (review.requesterKind === 'operator') {
    return `Prepared on the desk by staff${subject}; no shopper asked for this.`
  }
  if (review.requestedBySub) {
    return 'The original requester was signed in, but ownership of this customer record was not verified. This is separate from your Operator sign-in.'
  }
  return 'No verified requester identity was saved with this request. This is separate from your current Operator sign-in.'
}

export function requesterLabel(review: Pick<OperatorReview, 'requesterKind' | 'requestedBySub'>): string {
  if (review.requesterKind === 'shopper') return 'Requested by the verified shopper'
  if (review.requesterKind === 'operator') return 'Prepared by an operator'
  return review.requestedBySub
    ? 'Requester signed in; customer ownership unverified'
    : 'Original requester identity not recorded'
}

export interface OperatorReviewQueue {
  reviews: OperatorReview[]
  total: number
  pendingCount: number
}

export interface OperatorReplacement {
  replacementId: string
  reviewId: number
  orderId: number
  productId: string
  productName: string
  quantity: number
  disposition: string
  state: 'reserved' | 'awaiting_fulfillment' | 'outcome_unknown' | 'accepted' | 'shipped'
  workflowResolution: 'operator_review_required' | 'shipment_recorded' | null
  providerOperationId: string | null
  executionArn: string | null
  idempotencyKey: string
  approvalHash: string
  outbox: { eventId: string; attempts: number; publishedAt: string | null } | null
  provider: 'workshop-simulator'
  createdAt: string
  updatedAt: string
  events: { type: string; at: string; details: Record<string, unknown> }[]
}

export interface ReplacementRecovery {
  available: boolean
  replacements: OperatorReplacement[]
}

export function fetchReplacements(customerId: string, replacementId?: string): Promise<ReplacementRecovery> {
  const query = replacementId ? `?replacement_id=${encodeURIComponent(replacementId)}` : ''
  return request(`/api/operator/clients/${encodeURIComponent(customerId)}/replacements${query}`)
}

export function prepareReplacement(customerId: string, orderId: number, quantity: number, issue: string): Promise<{ reviewId: number }> {
  return request(`/api/operator/clients/${encodeURIComponent(customerId)}/replacements/prepare`, {
    method: 'POST', body: JSON.stringify({ orderId, quantity, issue }),
  })
}

export interface OperatorReviewDetail {
  review: OperatorReview
  /** Original reported context. Current business truth is resolved below on read. */
  shopperHandoff: ShopperHandoff | null
  /** Resolved from pellier.customers on read, never cached on the review. */
  client: {
    customerId: string
    name: string
    membership: Membership
    spend12mo: number
    note: string
    personaId: string | null
  }
  order: OperatorOrder | null
  product: {
    productId: string
    name: string
    brand: string
    price: number
    catalogQuantity: number
    imageUrl: string
  } | null
  /** Derived from live warehouse rows at read time. Never stored. */
  fulfilment: {
    totalUnits: number
    replacementAvailable: boolean
    /** False when no per-location row exists, so absence is not reported as zero. */
    availabilityVerified?: boolean
    warehouses: {
      warehouseId: string
      displayName: string
      city: string
      quantity: number
      shipWindowMin: number
      shipWindowMax: number
    }[]
  }
  /** pellier.orders has no status column; this is the real lifecycle. */
  returns: {
    returnId: number
    productId: string
    reason: string
    status: string
    requestedAt: string | null
    resolvedAt: string | null
  }[]
}

export interface OperatorReviewDecision {
  reviewId: number
  status: string
  humanState: ReviewHumanState
  decidedBy: string | null
  decidedAt: string | null
  assurance: ActionAssurance
}

export class OperatorApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    /** What the service said was missing, when it refused rather than failed. */
    public readonly missing: readonly string[] = [],
  ) {
    super(code)
    this.name = 'OperatorApiError'
  }

  /** True when the caller simply is not signed in as an operator. */
  get needsOperatorSignIn(): boolean {
    return this.status === 401 || this.status === 403
  }
}

/** Read APIs should surface an unavailable state, never leave the desk loading. */
export const OPERATOR_REQUEST_TIMEOUT_MS = 8_000
// A review hydrates current orders, inventory, returns, identity and receipts.
// Give this detail read its own bound without slowing failures on light reads.
export const OPERATOR_REVIEW_TIMEOUT_MS = 30_000

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = init.method === 'POST' ? 120_000 : OPERATOR_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(
    () => controller.abort(),
    timeoutMs,
  )
  try {
    const response = await apiFetch(path, {
      ...init,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...init.headers },
      signal: controller.signal,
    })
    if (!response.ok) {
      let code = response.status === 401 || response.status === 403
        ? 'operator_sign_in_required' : 'operator_unavailable'
      let missing: string[] = []
      try {
        const body = (await response.json()) as { detail?: unknown }
        const detail = body.detail
        if (typeof detail === 'string' && detail) {
          code = detail
        } else if (detail && typeof detail === 'object') {
          // A governed refusal is an object: `{ error, missing }`. Stringifying
          // it would put "[object Object]" in front of an operator.
          const shaped = detail as { error?: unknown; missing?: unknown }
          if (typeof shaped.error === 'string' && shaped.error) code = shaped.error
          if (Array.isArray(shaped.missing)) {
            missing = shaped.missing.filter((item): item is string => typeof item === 'string')
          }
        }
      } catch { /* Preserve the HTTP status when the response cannot be decoded. */ }
      throw new OperatorApiError(code, response.status, missing)
    }
    // The deadline includes the body, which can stall after headers arrive.
    return await response.json() as T
  } catch (error) {
    if (error instanceof OperatorApiError) throw error
    throw new OperatorApiError('operator_unavailable', 503)
  } finally {
    globalThis.clearTimeout(timeout)
  }
}

export function fetchClientBook(): Promise<OperatorBook> {
  return request<OperatorBook>('/api/operator/clients')
}

export function fetchClientRecord(
  customerId: string,
): Promise<OperatorClientRecord> {
  return request<OperatorClientRecord>(
    `/api/operator/clients/${encodeURIComponent(customerId)}`,
  )
}

/**
 * What the Operator can actually do right now.
 *
 * Backend-derived from live Gateway and policy state. The frontend must never
 * decide this: `initiate_return` is currently published with zero matching permits
 * while `issue_credit` is not published at all, and only the control plane can tell
 * those apart.
 */
export function fetchCapabilities(): Promise<CapabilitySnapshot> {
  return request<CapabilitySnapshot>('/api/operator/capabilities')
}

/**
 * Whether the composer may submit a development turn.
 *
 * Deliberately separate from capabilities: that reports governed business
 * capability, this reports whether orchestration exists to answer a question yet.
 * Collapsing them would make a governance state look like a missing feature.
 */
export function fetchConciergeConfig(): Promise<ConciergeConfig> {
  return request<ConciergeConfig>('/api/operator/concierge/config')
}

/** The latest Concierge session for a client, or null when none exists. */
export async function fetchLatestConciergeSession(
  clientId: string,
): Promise<string | null> {
  const body = await request<{ sessionId: string | null }>(
    `/api/operator/clients/${encodeURIComponent(clientId)}/concierge/sessions/latest`,
  )
  return body.sessionId ?? null
}

export function fetchConciergeSession(
  clientId: string,
  sessionId: string,
): Promise<ConciergeSession> {
  return request<ConciergeSession>(
    `/api/operator/clients/${encodeURIComponent(clientId)}` +
      `/concierge/sessions/${encodeURIComponent(sessionId)}`,
  )
}

/** Created lazily, when the operator first interacts — never on page load. */
export function createConciergeSession(clientId: string): Promise<ConciergeSession> {
  return request<ConciergeSession>(
    `/api/operator/clients/${encodeURIComponent(clientId)}/concierge/sessions`,
    { method: 'POST' },
  )
}

/**
 * How a turn is submitted. The only way, from the browser.
 *
 * Streamed so the operator sees real progress instead of seven seconds of stillness.
 * The backend also exposes a non-streaming `/turns` for curl-based proof, but the
 * browser does not use it: two client paths to one turn would drift.
 *
 * SSE over `fetch` + `getReader()`, matching how `services/chat.ts` already consumes
 * the agent stream. `onStep` fires for work the backend has actually finished; the
 * single `running` event is a genuine state, not a simulated tick.
 */
export async function streamConciergeTurn(
  clientId: string,
  sessionId: string,
  message: string,
  transportKey: string,
  onStep: (step: ConciergeInvestigationStep) => void,
  onAnswer: (answer: ConciergeStreamAnswer) => void,
  signal?: AbortSignal,
): Promise<ConciergeTurn & Record<string, unknown>> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) cancel()
  // Bound a cold managed turn without imposing the short read-API deadline.
  const deadline = globalThis.setTimeout(cancel, 300_000)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
  const response = await apiFetch(
    `/api/operator/clients/${encodeURIComponent(clientId)}` +
      `/concierge/sessions/${encodeURIComponent(sessionId)}/turns/stream`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ message, transportKey }),
      signal: controller.signal,
    },
  )
  if (!response.ok || !response.body) {
    throw new OperatorApiError('operator_unavailable', response.status || 503)
  }

  reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let final: (ConciergeTurn & Record<string, unknown>) | null = null

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE frames are separated by a blank line.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      let event = ''
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      const parsed = JSON.parse(data)
      if (event === 'step') onStep(parsed as ConciergeInvestigationStep)
      else if (event === 'answer') onAnswer(parsed as ConciergeStreamAnswer)
      else if (event === 'complete') final = parsed
      else if (event === 'error') {
        throw new OperatorApiError(parsed.detail ?? 'operator_unavailable', 500)
      }
    }
  }

  if (!final) throw new OperatorApiError('operator_unavailable', 500)
  return final
  } finally {
    globalThis.clearTimeout(deadline)
    signal?.removeEventListener('abort', cancel)
    try { await reader?.cancel?.() } catch { /* The connection may already be closed. */ }
    reader?.releaseLock?.()
  }
}

export function fetchReviewQueue(): Promise<OperatorReviewQueue> {
  return request<OperatorReviewQueue>('/api/operator/reviews')
}

export function fetchReview(reviewId: number): Promise<OperatorReviewDetail> {
  return request<OperatorReviewDetail>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}`,
    {},
    OPERATOR_REVIEW_TIMEOUT_MS,
  )
}

/**
 * Confirm the exact proposed action.
 *
 * `actionHash` is the fingerprint the console displayed. Echoing it is what
 * makes the confirmation bind to those parameters: if any material value moved,
 * the server refuses with `parameters_changed` rather than applying a stale
 * consent to new values.
 *
 * This records a human decision. It performs no business mutation.
 */
export function confirmReview(
  reviewId: number,
  actionHash: string,
): Promise<OperatorReviewDecision> {
  return request<OperatorReviewDecision>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/confirm`,
    { method: 'POST', body: JSON.stringify({ actionHash }) },
  )
}

/** Decline. Nothing is submitted anywhere; no fingerprint is required. */
export function declineReview(
  reviewId: number,
): Promise<OperatorReviewDecision> {
  return request<OperatorReviewDecision>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/decline`,
    { method: 'POST' },
  )
}

/**
 * Execute the confirmed action through the governed rail.
 *
 * Carries no action parameters. The customer, tool, reason, and amount all come
 * from the persisted review, so a browser cannot execute a different mutation
 * than the one a human confirmed. `expectedActionHash` is stale-view protection
 * only.
 */
export function executeReview(
  reviewId: number,
  expectedActionHash?: string,
): Promise<OperatorExecutionResult> {
  return request<OperatorExecutionResult>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/execute`,
    {
      method: 'POST',
      body: JSON.stringify(
        expectedActionHash ? { expectedActionHash } : {},
      ),
    },
  )
}
