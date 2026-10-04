/**
 * Pellier Operator API client.
 *
 * Every route requires a verified staff token, so 401 and 403 are real states
 * the desk renders rather than errors to swallow. Every field comes from
 * PostgreSQL/Aurora: there is no committed frontend copy of the clients,
 * because UI state is not evidence.
 */
import { apiFetch } from './apiBase'
import type { TurnStep } from '../components/turn/turnTypes'

export interface OperatorClient {
  customerId: string
  /** `CUST-JESSICA` -> `jessica`. Drives the portrait filename. */
  slug: string
  name: string
  /** Set for the four shoppers, who have a portrait and a storefront sign-in. */
  personaId: string | null
  /** Open or pending support tickets: what staff act on. */
  openRequests: number
  openRequest: string | null
  openRequestStatus: string | null
  lastOrder: { productName: string; placedAt: string | null } | null
}

export interface OperatorBook {
  clients: OperatorClient[]
  total: number
  openRequests: number
}

export interface OperatorClientSummary {
  customerId: string
  slug: string
  name: string
  personaId: string | null
  openTicketCount: number
  returnedCount: number
  creditBalanceCents: number
  creditBalance: string
}

export interface OperatorOrder {
  orderId: number
  productId: string
  productName: string
  brand: string
  amountPaidCents: number
  /** Formatted once by the API so no surface re-derives currency from cents. */
  amountPaid: string
  quantity: number
  placedAt: string | null
  imageUrl: string
  /** The authoritative return state, from `pellier.returns`. */
  returnStatus?: string | null
  returned?: boolean
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
  amount: string
  currency: string
  reason: string
  issuedBy: string | null
  idempotencyKey: string
  createdAt: string | null
}

export interface OperatorClientRecord {
  dataSource?: string
  client: OperatorClientSummary
  orders: OperatorOrder[]
  tickets: OperatorTicket[]
  credits: OperatorCredit[]
  /** This client's credit reviews, open first, so the record can say "waiting for approval". */
  reviews: OperatorReview[]
}

/**
 * The four assurance axes, exactly as the API resolved them.
 *
 * Independent on purpose: a single boolean would let a human decision imply an
 * authorization decision, so the desk renders these verbatim and never derives
 * one from another.
 */
export interface ActionAssurance {
  human: 'CONFIRMATION_REQUIRED' | 'CONFIRMED' | 'DECLINED'
  policy: 'PENDING' | 'NOT_EVALUATED' | 'ALLOW' | 'DENY' | 'EVALUATION_INCOMPLETE'
  aurora: 'NOT_EVALUATED' | 'NOT_REACHED' | 'PERMITTED' | 'DENIED' | 'OUTCOME_UNKNOWN'
  evidence: 'PENDING' | 'NO_EXECUTION' | 'RECEIPTED' | 'POLICY_PROOF' | 'ATTEMPT_RECEIPT'
}

/** What the two durable tables hold for one write key, counted from the tables. */
export interface ExecutionRecord {
  idempotencyKey: string
  creditRows: number
  creditIds: number[]
  amountCents: number | null
  auditRows: number
  auditIds: number[]
  readable: boolean
}

/** One governed execution attempt. Each axis comes from its own artifact. */
export interface OperatorExecutionResult {
  reviewId: number
  rail: 'gateway-mcp' | 'in-process' | 'refused'
  executionTurnId: string
  idempotencyKey: string
  actorPrincipal: string
  customerSubject: string | null
  assurance: ActionAssurance
  notes: Partial<Record<'policy' | 'aurora' | 'audit' | 'rail' | 'evidence', string>>
  tool: string
  result: Record<string, unknown>
  record: ExecutionRecord
}

/** A stored execution receipt: what the governance layers decided, and what decided it. */
export interface OperatorExecutionReceipt {
  receiptId: number
  executionTurnId: string
  tool: string
  gatewayActionId: string
  rail: 'gateway-mcp' | 'in-process' | 'refused'
  actorPrincipal: string
  customerSubject: string | null
  policyEngineId: string
  gatewayMode: string
  matchingForbids: string[]
  idempotencyKey: string
  notes: Partial<Record<'policy' | 'aurora' | 'audit' | 'rail' | 'evidence', string>>
  recordedAt: string | null
}

export type ReviewHumanState = 'confirmation_required' | 'confirmed' | 'declined'

/** Workflow state and references. Never business truth. */
export interface OperatorReview {
  reviewId: number
  customerId: string
  customerName: string
  slug: string
  personaId: string | null
  action: string
  parameters: Record<string, unknown>
  amountCents: number | null
  amount: string | null
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  humanState: ReviewHumanState
  assurance: ActionAssurance
  sourceTurnId: string | null
  executionTurnId: string | null
  execution: OperatorExecutionReceipt | null
  orderId: number | null
  orderIds: number[]
  issue: string
  recommendation: {
    primaryAction?: string
    rationale?: string
    orderIds?: number[]
    items?: string[]
    investigationTurnId?: string
  }
  /** Fingerprint of the parameters shown, echoed back on confirm. */
  actionHash: string
  decidedBy: string | null
  requestedBySub: string | null
  requesterKind: 'shopper' | 'operator' | 'unverified'
  requestedAt: string | null
  decidedAt: string | null
}

export interface OperatorReviewQueue {
  reviews: OperatorReview[]
  total: number
  pendingCount: number
}

export interface OperatorReviewDetail {
  review: OperatorReview
  client: { customerId: string; name: string; slug: string; personaId: string | null }
  /** The orders the proposal refers to, read now from the order table. */
  orders: OperatorOrder[]
  /** Null until an execution has been attempted. */
  record: ExecutionRecord | null
}

export interface OperatorReviewDecision {
  reviewId: number
  status: string
  humanState: ReviewHumanState
  decidedBy: string | null
  decidedAt: string | null
  assurance: ActionAssurance
}

/** The Planner's proposal, as the investigation stream reports it. */
export interface InvestigationProposal {
  reviewId: number
  customerId: string
  amountCents: number
  amount: string
  reason: string
  orderIds: number[]
  actionHash: string
  idempotencyKey: string
  status: 'pending'
}

/** The `answer` and `complete` events of one investigation. */
export interface InvestigationAnswer {
  turnId: string
  customerId: string
  status: 'complete' | 'failed'
  investigation: { facts: string[]; missing: string[] }
  planner: string
  proposal: InvestigationProposal | null
  graph: {
    graphId: string
    pattern: string
    execution: string
    modelId: string
    nodes: { nodeId: string; status: string; durationMs: number }[]
    durationMs: number
  }
  error: string | null
}

export function requesterLine(review: Pick<OperatorReview, 'requesterKind' | 'requestedBySub'>): string {
  if (review.requesterKind === 'operator') return 'Proposed by the Planner on the desk.'
  if (review.requesterKind === 'shopper') return 'Asked for by the signed-in shopper.'
  if (review.requestedBySub) {
    return 'The requester was signed in, but ownership of this customer record was not verified.'
  }
  return 'No verified requester identity was saved with this request.'
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

  /** True when the caller simply is not signed in as staff. */
  get needsOperatorSignIn(): boolean {
    return this.status === 401 || this.status === 403
  }
}

/** Read APIs should surface an unavailable state, never leave the desk loading. */
export const OPERATOR_REQUEST_TIMEOUT_MS = 8_000
export const OPERATOR_REVIEW_TIMEOUT_MS = 30_000

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = init.method === 'POST' ? 120_000 : OPERATOR_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs)
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
          const shaped = detail as { error?: unknown; missing?: unknown }
          if (typeof shaped.error === 'string' && shaped.error) code = shaped.error
          if (Array.isArray(shaped.missing)) {
            missing = shaped.missing.filter((item): item is string => typeof item === 'string')
          }
        }
      } catch { /* Preserve the HTTP status when the response cannot be decoded. */ }
      throw new OperatorApiError(code, response.status, missing)
    }
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

export function fetchClientRecord(customerId: string): Promise<OperatorClientRecord> {
  return request<OperatorClientRecord>(`/api/operator/clients/${encodeURIComponent(customerId)}`)
}

/**
 * Run the investigation for one client and relay its stream.
 *
 * SSE over `fetch` + `getReader()`, matching how the shopper's turn is read.
 * `onStep` fires for each `step` event, in the shape `StepList` renders;
 * `onAnswer` once with the brief and the proposal. The returned promise
 * settles on `complete`.
 */
export async function streamInvestigation(
  customerId: string,
  onStep: (step: TurnStep) => void,
  onAnswer: (answer: InvestigationAnswer) => void,
  signal?: AbortSignal,
): Promise<InvestigationAnswer> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) cancel()
  const deadline = globalThis.setTimeout(cancel, 300_000)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
    const response = await apiFetch(
      `/api/operator/clients/${encodeURIComponent(customerId)}/investigate`,
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        signal: controller.signal,
      },
    )
    if (!response.ok || !response.body) {
      throw new OperatorApiError(
        response.status === 401 || response.status === 403 ? 'operator_sign_in_required' : 'operator_unavailable',
        response.status || 503,
      )
    }
    reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let final: InvestigationAnswer | null = null
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
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
        if (event === 'step') onStep(parsed as TurnStep)
        else if (event === 'answer') onAnswer(parsed as InvestigationAnswer)
        else if (event === 'complete') final = parsed as InvestigationAnswer
        else if (event === 'error') {
          throw new OperatorApiError(parsed.detail ?? 'investigation_failed', 500)
        }
      }
    }
    if (!final) throw new OperatorApiError('investigation_failed', 500)
    return final
  } catch (error) {
    if (error instanceof OperatorApiError) throw error
    throw new OperatorApiError(controller.signal.aborted ? 'investigation_stopped' : 'operator_unavailable', 503)
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
 * Confirm the exact proposed credit.
 *
 * `actionHash` is the fingerprint the desk displayed. Echoing it is what makes
 * the confirmation bind to those parameters: if any material value moved, the
 * server refuses with `parameters_changed` rather than applying a stale
 * consent to new values. This records a decision; it performs no mutation.
 */
export function confirmReview(reviewId: number, actionHash: string): Promise<OperatorReviewDecision> {
  return request<OperatorReviewDecision>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/confirm`,
    { method: 'POST', body: JSON.stringify({ actionHash }) },
  )
}

/** Decline. Nothing is submitted anywhere; no fingerprint is required. */
export function declineReview(reviewId: number): Promise<OperatorReviewDecision> {
  return request<OperatorReviewDecision>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/decline`,
    { method: 'POST' },
  )
}

/**
 * Execute the confirmed credit through the configured rail.
 *
 * Carries no action parameters. The customer, reason and amount all come from
 * the persisted review, so a browser cannot execute a different credit than
 * the one a person confirmed. `expectedActionHash` is stale-view protection.
 */
export function executeReview(reviewId: number, expectedActionHash?: string): Promise<OperatorExecutionResult> {
  return request<OperatorExecutionResult>(
    `/api/operator/reviews/${encodeURIComponent(String(reviewId))}/execute`,
    { method: 'POST', body: JSON.stringify(expectedActionHash ? { expectedActionHash } : {}) },
  )
}
