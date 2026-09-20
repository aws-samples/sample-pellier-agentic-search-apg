/**
 * Chat Service - Connects to FastAPI Backend
 * Handles product search and AI chat functionality
 */

import { API_BASE_URL } from './apiBase'

export const CHAT_ERROR_CODES = [
  'policy_denied',
  'authentication_required',
  'rate_limited',
  'request_timeout',
  'service_unavailable',
  'invalid_request',
  'stream_interrupted',
  'network_error',
  'request_failed',
  'workshop_build_required',
] as const

export type ChatErrorCode = (typeof CHAT_ERROR_CODES)[number]

const CHAT_ERROR_CODE_SET = new Set<string>(CHAT_ERROR_CODES)
const STREAM_TIMEOUT_MS = 130_000

export class ChatServiceError extends Error {
  readonly code: ChatErrorCode
  readonly status?: number
  readonly retryable: boolean
  readonly referenceId?: string

  constructor(
    message: string,
    options: {
      code: ChatErrorCode
      status?: number
      retryable?: boolean
      referenceId?: string
    },
  ) {
    super(message)
    this.name = 'ChatServiceError'
    this.code = options.code
    this.status = options.status
    this.retryable = options.retryable ?? isRetryableCode(options.code)
    this.referenceId = options.referenceId
  }
}

function isRetryableCode(code: ChatErrorCode): boolean {
  return ![
    'policy_denied',
    'authentication_required',
    'invalid_request',
    'workshop_build_required',
  ].includes(code)
}

function isChatErrorCode(value: unknown): value is ChatErrorCode {
  return typeof value === 'string' && CHAT_ERROR_CODE_SET.has(value)
}

function inferErrorCode(detail: string, status?: number): ChatErrorCode {
  const normalized = detail.toLowerCase()
  // Transport truth wins over prose matching. A reverse proxy, model runtime,
  // or expired session can all use words such as "AccessDenied" or "not
  // authorized"; none of those phrases alone proves that Pellier's active
  // AgentCore Policy produced a DENY decision. Structured stream errors already
  // carry an explicit `policy_denied` code and bypass this inference.
  if (
    status === 401 ||
    status === 403 ||
    normalized.includes('invalid bearer') ||
    normalized.includes('expired token') ||
    normalized.includes('token expired') ||
    normalized.includes('401 unauthorized')
  ) {
    return 'authentication_required'
  }
  if (
    status === 429 ||
    normalized.includes('throttlingexception') ||
    normalized.includes('rate limit') ||
    normalized.includes('too many requests')
  ) {
    return 'rate_limited'
  }
  if (
    status === 408 ||
    status === 504 ||
    normalized.includes('timed out') ||
    normalized.includes('timeout')
  ) {
    return 'request_timeout'
  }
  if (
    status === 503 ||
    (status !== undefined && status >= 500) ||
    normalized.includes('service unavailable') ||
    normalized.includes('connection refused')
  ) {
    return 'service_unavailable'
  }
  const policyMarkers = [
    'authorizeactionexception',
    'accessdeniedexception',
    'explicit deny',
    'not authorized',
    'authorization failed',
    'not allowed due to policy',
    'policy enforcement',
    'access denied by policy',
  ]
  if (policyMarkers.some(marker => normalized.includes(marker))) {
    return 'policy_denied'
  }
  // 404 is NOT a wording problem. It means the route is not there — a wrong
  // backend target, a dev proxy pointed at the other branch's port, or a
  // half-started service. Classing it as invalid_request tells the shopper to
  // "adjust the request and send it again", so they retype a perfectly good
  // question while the real fault is infrastructure. Keep 400/422 (genuine
  // request validation) separate from a missing endpoint.
  if (status === 404) {
    return 'service_unavailable'
  }
  if (status === 400 || status === 422) {
    return 'invalid_request'
  }
  return 'request_failed'
}

function messageFromPayload(payload: unknown): string {
  if (typeof payload === 'string') return payload
  if (!payload || typeof payload !== 'object') return ''
  const record = payload as Record<string, unknown>
  for (const key of ['detail', 'message', 'error']) {
    if (typeof record[key] === 'string') return record[key]
  }
  return ''
}

async function errorFromResponse(response: Response): Promise<ChatServiceError> {
  let payload: unknown = null
  let raw = ''
  try {
    raw = await response.text()
    payload = raw ? JSON.parse(raw) : null
  } catch {
    payload = raw
  }
  const detail = messageFromPayload(payload) || `HTTP ${response.status}`
  return new ChatServiceError(detail, {
    code: inferErrorCode(detail, response.status),
    status: response.status,
  })
}

function errorFromStreamEvent(data: Record<string, unknown>): ChatServiceError {
  const detail = messageFromPayload(data) || 'The response stream failed.'
  const code = isChatErrorCode(data.code)
    ? data.code
    : inferErrorCode(detail)
  return new ChatServiceError(detail, {
    code,
    retryable:
      typeof data.retryable === 'boolean' ? data.retryable : undefined,
    referenceId:
      typeof data.reference_id === 'string' ? data.reference_id : undefined,
  })
}

export function normalizeChatError(error: unknown): ChatServiceError {
  if (error instanceof ChatServiceError) return error
  if (error instanceof Error && error.name === 'AbortError') {
    return new ChatServiceError('The response stream timed out.', {
      code: 'request_timeout',
    })
  }
  if (error instanceof TypeError) {
    return new ChatServiceError(error.message || 'Network request failed.', {
      code: 'network_error',
    })
  }
  const detail = error instanceof Error ? error.message : String(error || '')
  return new ChatServiceError(detail || 'The request failed.', {
    code: inferErrorCode(detail),
  })
}

/**
 * Get or create session ID for conversation persistence
 */
function getSessionId(): string {
  let sessionId = localStorage.getItem('pellier-session-id')
  if (!sessionId) {
    sessionId = `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    localStorage.setItem('pellier-session-id', sessionId)
  }
  return sessionId
}

function getAuthHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
}

import type {
  ExecutionRail,
  RailDecision,
  RailDegradation,
} from '../shared/governedTypes'
import type { EvidenceLedger } from '../shared/evidenceLedger'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  products?: ChatProduct[]
  suggestions?: string[]
}

export interface ChatProduct {
  id: number
  name: string
  price: number
  image: string
  category?: string
  rating?: number
  reviews?: number
  url?: string
  similarityScore?: number
  quantity?: number
  inStock?: boolean
  availability?: ChatProductAvailability
  ownership?: 'owned'
  originalPrice?: number
  discountPercent?: number
}

export interface ChatProductAvailability {
  status: string
  availableQuantity?: number | null
}

function renderedProductsForHistory(message: ChatMessage): ChatProduct[] {
  const products = message.products ?? []
  const normalizedContent = message.content.toLowerCase()

  return products
    .map((product, index) => ({
      product,
      index,
      mentionIndex: product.name
        ? normalizedContent.indexOf(product.name.toLowerCase())
        : -1,
    }))
    .filter((item) => item.mentionIndex >= 0)
    .sort((a, b) =>
      a.mentionIndex === b.mentionIndex
        ? a.index - b.index
        : a.mentionIndex - b.mentionIndex,
    )
    .map((item) => item.product)
    .slice(0, 3)
}

export interface AgentExecution {
  agent_steps: Array<{agent: string, action: string, status: string, timestamp: number, duration_ms: number}>
  tool_calls: Array<{tool: string, params?: string, timestamp: number, duration_ms: number, status: string}>
  reasoning_steps: Array<{step: string, content: string, timestamp: number}>
  trace_id?: string | null
  traceIds?: string[]
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    span_count: number
    source: string
  }
  total_duration_ms: number
  success_rate: number
  /** False when Strands' TracerProvider isn't SDK-backed. UI renders a
   * banner and disables the waterfall instead of synthesizing spans. */
  otel_enabled?: boolean
  /** Actionable failure string from the backend when otel_enabled is
   * false. Rendered verbatim. */
  reason?: string
}

export interface ChatResponse {
  response: string
  products: ChatProduct[]
  suggestions?: string[]
  agent_execution?: AgentExecution
  /**
   * Stable per-turn identifier minted server-side (`app.new_turn_id`).
   * Used to deep-link this exact turn's evidence in Observatory. Optional
   * because a turn served from smoke mode or an older backend emits none —
   * consumers must degrade to a session-scoped link rather than invent one.
   */
  turn_id?: string
  /** Session the turn belongs to, echoed back by the backend. */
  session_id?: string
  /** Rail that actually served the turn (`services/execution_rail.py`). */
  rail?: ExecutionRail
  /** Full rail decision, including degraded reasons. */
  railDecision?: RailDecision
  /** Present only when the governed rail was requested and unavailable. */
  degradation?: RailDegradation
  /** Canonical, principal-scoped projection returned after durable persistence. */
  evidence_ledger?: EvidenceLedger
  orchestrator_enabled?: boolean
  token_count?: number
  estimated_cost_usd?: number
  cost_breakdown?: {
    llm_cost?: number
    embedding_cost?: number
    token_source?: string
    pricing_source?: string
    rate_per_1k_tokens_usd?: number
    prompt_tokens?: number
    completion_tokens?: number
    usage_span_count?: number
  }
}

export type ResponseMode = 'balanced' | 'editorial' | 'fast'
export type OrchestrationPattern =
  | 'dispatcher'
  | 'agents_as_tools'
  | 'graph'

/**
 * Send a chat message with streaming support
 */
export async function sendChatMessageStreaming(
  query: string,
  conversationHistory: ChatMessage[] = [],
  onUpdate: (data: any) => void,
  workshopMode?: string,
  guardrailsEnabled?: boolean,
  customerId?: string | null,
  pattern?: OrchestrationPattern | null,
  responseMode: ResponseMode = 'balanced',
  /**
   * Caller-owned cancellation, e.g. a component unmounting mid-stream.
   * Forwarded onto the internal controller so one `fetch` call still
   * answers to both the timeout below and the caller's own lifecycle.
   */
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS)
  const forwardAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', forwardAbort)
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: getAuthHeaders(),
      signal: controller.signal,
      body: JSON.stringify({
        message: query,
        conversation_history: conversationHistory.map(msg => ({
          role: msg.role,
          content: msg.content,
          // Keep the last rendered cards available to the next turn so a
          // reference such as "that pair" retains exact product identity.
          // Backend tools still own any current price or stock answer.
          products: renderedProductsForHistory(msg).map(product => ({
            id: product.id,
            name: product.name,
            price: product.price,
            category: product.category,
            availability: product.availability?.status,
            ownership: product.ownership,
          })),
        })),
        session_id: getSessionId(),
        workshop_mode: workshopMode || null,
        guardrails_enabled: guardrailsEnabled || false,
        customer_id: customerId ?? null,
        pattern: pattern ?? null,
        response_mode: responseMode,
      }),
    })

    if (!response.ok) {
      throw await errorFromResponse(response)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new ChatServiceError('The response did not include a stream.', {
        code: 'stream_interrupted',
      })
    }

    const decoder = new TextDecoder()
    let finalResponse: ChatResponse | null = null
    let lastContent = ''
    let streamError: ChatServiceError | null = null
    // Turn identity arrives on the first `turn_start` event, before any
    // content. Held here so the assembled response carries it even when
    // the terminal `complete` event omits it.
    let streamTurnId: string | null = null
    let streamSessionId: string | null = null

    const processLine = (line: string) => {
      if (!line.startsWith('data:')) return

      let data: Record<string, any>
      try {
        data = JSON.parse(line.slice(5).trimStart())
      } catch {
        return
      }

      onUpdate(data)
      if (data.type === 'error') {
        streamError = errorFromStreamEvent(data)
        return
      }
      if (data.type === 'build_required') {
        // An expected workshop state, sent outside the error channel so the
        // stream completes cleanly. The storefront still treats it as a
        // terminal outcome with its own card: the participant wording in
        // `message` is never rendered to a shopper, and the backend's code
        // travels as the reference so the lab guide can name it.
        streamError = new ChatServiceError(
          messageFromPayload(data) || 'This capability is not built yet.',
          {
            code: 'workshop_build_required',
            retryable: false,
            referenceId:
              typeof data.code === 'string' ? data.code : 'workshop_build_required',
          },
        )
        return
      }

      if (data.type === 'content') {
        lastContent = data.content
      } else if (data.type === 'content_delta') {
        lastContent += data.delta
      } else if (data.type === 'turn_start') {
        // First event of the stream: the backend's turn identity. Captured
        // here so it is available even if the stream errors before
        // `complete` — a failed turn still has evidence worth linking to.
        if (typeof data.turn_id === 'string') streamTurnId = data.turn_id
        if (typeof data.session_id === 'string') streamSessionId = data.session_id
      } else if (data.type === 'complete') {
        finalResponse = {
          response: data.response?.response,
          products: data.response?.products || [],
          suggestions: data.response?.suggestions || [],
          agent_execution: data.response?.agent_execution,
          turn_id: data.response?.turn_id ?? streamTurnId ?? undefined,
          session_id: data.response?.session_id ?? streamSessionId ?? undefined,
          rail: data.response?.rail,
          railDecision: data.response?.railDecision,
          degradation: data.response?.degradation,
          evidence_ledger: data.response?.evidence_ledger,
          orchestrator_enabled: data.response?.orchestrator_enabled,
          token_count: data.response?.token_count,
          estimated_cost_usd: data.response?.estimated_cost_usd,
          cost_breakdown: data.response?.cost_breakdown,
        }
      }
    }

    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      lines.forEach(processLine)
      if (streamError) {
        await reader.cancel()
        throw streamError
      }
    }

    buffer += decoder.decode()
    if (buffer.trim()) processLine(buffer)
    if (streamError) throw streamError
    if (!finalResponse) {
      throw new ChatServiceError(
        lastContent
          ? 'The response stream ended before it was confirmed complete.'
          : 'The response stream ended without a result.',
        { code: 'stream_interrupted' },
      )
    }

    return finalResponse
  } catch (error) {
    throw normalizeChatError(error)
  } finally {
    globalThis.clearTimeout(timeout)
    signal?.removeEventListener('abort', forwardAbort)
  }
}

/**
 * Health check for the backend.
 *
 * @param signal Optional abort signal. Pass one with a deadline: a health
 *   endpoint that hangs is indistinguishable from one that is healthy but
 *   slow, and a caller that waits forever reports the wrong answer forever.
 * @returns True only when the endpoint answered with a success status.
 */
export async function checkBackendHealth(
  signal?: AbortSignal,
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`, {
      method: 'GET',
      signal,
    })
    return response.ok
  } catch {
    return false
  }
}
