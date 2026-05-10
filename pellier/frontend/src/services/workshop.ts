/**
 * Workshop telemetry API client.
 *
 * Thin fetch wrapper around `POST /api/atelier/query`. Intentionally
 * separate from `services/chat.ts` (ConciergeModal's SSE path) because
 * the shapes don't overlap — workshop returns a flat
 * `{session_id, events: WorkshopEvent[]}` payload, chat streams SSE
 * frames carrying products and cart ops.
 *
 * The `events` contract matches the Coffee Roastery reference
 * (`conferences/2026-postgresconf-agentic-ai/static/index.html`
 * playEvents()). The panel renderer ports 1:1 — no transformation.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

export type WorkshopEventType = 'plan' | 'step' | 'panel' | 'text' | 'response'

export interface WorkshopPlanEvent {
  type: 'plan'
  title: string
  steps: string[]
  duration_ms: number
  ts_ms: number
}

export interface WorkshopStepEvent {
  type: 'step'
  index: number
  state: 'active' | 'done'
  ts_ms: number
}

export interface WorkshopPanelEvent {
  type: 'panel'
  agent: string
  tag: string
  tag_class: 'cyan' | 'amber' | 'green'
  title: string
  sql: string
  columns: string[]
  rows: string[][]
  meta: string
  duration_ms: number
  ts_ms: number
  /**
   * 1-based position of this panel in the turn's panel stream.
   * Stamped by the backend's ``AgentContext.emit_panel``. Citation
   * pills ("trace 7") resolve to the panel with ``trace_index === 7``.
   * Optional for backwards compatibility with pre-trace-index events.
   */
  trace_index?: number
}

export interface WorkshopCitation {
  k: string
  ref: string
}

export interface WorkshopTextEvent {
  type: 'text'
  text: string
  ts_ms: number
}

export interface WorkshopResponseEvent {
  type: 'response'
  text: string
  citations: WorkshopCitation[]
  confidence: number | null
  ts_ms: number
}

export type WorkshopEvent =
  | WorkshopPlanEvent
  | WorkshopStepEvent
  | WorkshopPanelEvent
  | WorkshopTextEvent
  | WorkshopResponseEvent

export interface WorkshopQueryRequest {
  query: string
  session_id?: string | null
  customer_id?: string | null
}

export interface WorkshopQueryResponse {
  session_id: string
  events: WorkshopEvent[]
}

// ---------------------------------------------------------------------------
// Turn primitive
// ---------------------------------------------------------------------------

/**
 * A Turn groups the user's query with the full event bundle the agent
 * emitted in response, categorized so the renderer can compose the
 * interleaved Atelier chat (text → plan chip → tool chips → text →
 * products → text → confidence) without re-scanning the event list
 * each render.
 *
 * Special-tag panels are lifted out of ``panels`` so the renderer
 * handles them as first-class UI primitives rather than as generic
 * tool chips:
 *   - PLAN panel       → ``plan`` (rendered as PlanPreviewChip)
 *   - MEMORY · CONFIDENCE → ``confidence`` (rendered as ConfidenceSummary)
 *   - RECOMMENDATION panels whose rows describe products →
 *     ``products`` (rendered as ProductMiniCard grid)
 *
 * ``panels`` retains everything else (tool calls, memory queries,
 * guardrails, grounding) in event-emission order.
 */

export interface TurnProduct {
  product_id?: string
  name: string
  price?: string
  attributes?: string
  /** Optional color block hex for the placeholder visual. */
  tone?: string
}

export interface Turn {
  id: string
  user_text: string
  assistant_text: string | null
  plan?: WorkshopPlanEvent
  /** All panels except PLAN, MEMORY · CONFIDENCE, RECOMMENDATION. */
  panels: WorkshopPanelEvent[]
  confidence?: WorkshopPanelEvent
  products?: TurnProduct[]
  citations?: WorkshopCitation[]
  /** Narrative text fragments emitted between panels ("Looking through..."). */
  text_fragments?: string[]
  /**
   * True when this turn is the synthetic "welcome-back" resume that
   * fires on customer change with no session yet. The user never
   * typed the ``user_text``; the UserMessage renders italic + muted
   * to make that visible.
   */
  resumed?: boolean
}

const CONFIDENCE_TAG = 'MEMORY · CONFIDENCE'
const RECOMMENDATION_TAG_RE = /^RECOMMENDATION /

/**
 * Turn the raw events of a single submit into a Turn.
 *
 * Pure function — pass it the user's prompt text and the events
 * returned by /api/atelier/query for that prompt. Safe to call from
 * ``useMemo``; idempotent for the same inputs.
 */
export function eventsToTurn(
  id: string,
  userText: string,
  events: WorkshopEvent[],
): Turn {
  let plan: WorkshopPlanEvent | undefined
  let confidence: WorkshopPanelEvent | undefined
  let recommendationPanel: WorkshopPanelEvent | undefined
  const panels: WorkshopPanelEvent[] = []
  let assistantText: string | null = null
  let citations: WorkshopCitation[] | undefined
  const textFragments: string[] = []

  for (const ev of events) {
    if (ev.type === 'plan') {
      plan = ev
    } else if (ev.type === 'panel') {
      if (ev.tag === CONFIDENCE_TAG) {
        confidence = ev
      } else if (RECOMMENDATION_TAG_RE.test(ev.tag)) {
        recommendationPanel = ev
      } else {
        panels.push(ev)
      }
    } else if (ev.type === 'text') {
      textFragments.push(ev.text)
    } else if (ev.type === 'response') {
      assistantText = ev.text
      if (ev.citations && ev.citations.length > 0) citations = ev.citations
    }
  }

  const products = recommendationPanel
    ? recommendationPanelToProducts(recommendationPanel)
    : undefined

  return {
    id,
    user_text: userText,
    assistant_text: assistantText,
    plan,
    panels,
    confidence,
    products,
    citations,
    text_fragments: textFragments.length > 0 ? textFragments : undefined,
  }
}

/**
 * Lift a RECOMMENDATION panel's rows into TurnProduct shapes so the
 * chat can render ProductMiniCards. The panel's column order is the
 * backend's contract; we tolerate extra columns and fill what we can.
 *
 * Heuristic columns (backend emits some combination of these):
 *   name, price, attrs, product_id
 *
 * If columns don't match, fall back to whatever's there.
 */
function recommendationPanelToProducts(
  panel: WorkshopPanelEvent,
): TurnProduct[] {
  const cols = panel.columns.map((c) => c.toLowerCase())
  const ixOf = (key: string) => cols.indexOf(key)
  const nameIx = ixOf('name') >= 0 ? ixOf('name') : 0
  const priceIx = ixOf('price')
  const attrsIx = ixOf('attrs') >= 0 ? ixOf('attrs') : ixOf('attributes')
  const idIx = ixOf('product_id') >= 0 ? ixOf('product_id') : ixOf('id')

  return panel.rows.map((row) => ({
    product_id: idIx >= 0 ? row[idIx] : undefined,
    name: row[nameIx] ?? '(unnamed)',
    price: priceIx >= 0 ? row[priceIx] : undefined,
    attributes: attrsIx >= 0 ? row[attrsIx] : undefined,
  }))
}

// ---------------------------------------------------------------------------
// Minimum-reveal floor per event type (ms). Events that arrive faster
// than the floor are held so fast Postgres reads don't flicker past.
// Events that arrive slower display immediately. Configurable here.
// ---------------------------------------------------------------------------
const REVEAL_FLOOR: Record<string, number> = {
  plan: 200,
  step_active: 80,
  step_done: 60,
  panel_llm: 400,
  panel_memory: 150,
  panel_other: 180,
  text: 120,
  response: 250,
  meta: 0,
}

function floorKeyForEvent(ev: WorkshopEvent | { type: 'meta' }): string {
  if (ev.type === 'step') return `step_${(ev as WorkshopStepEvent).state}`
  if (ev.type === 'panel') {
    const tag = (ev as WorkshopPanelEvent).tag
    if (tag.startsWith('LLM')) return 'panel_llm'
    if (tag.startsWith('MEMORY')) return 'panel_memory'
    return 'panel_other'
  }
  return ev.type
}

/**
 * Stream a workshop query via SSE. Calls ``onEvent`` for each event
 * as it arrives from the backend, respecting minimum-reveal floors
 * so fast events don't flicker past.
 *
 * Returns the session_id from the meta event.
 */
export async function queryWorkshopStream(
  req: WorkshopQueryRequest,
  onEvent: (ev: WorkshopEvent) => void,
): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE_URL}/api/atelier/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: req.query,
      session_id: req.session_id ?? null,
      customer_id: req.customer_id ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`workshop query failed (${res.status}): ${body || res.statusText}`)
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sessionId = ''
  let lastRevealAt = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Parse SSE lines: "data: <json>\n\n"
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // keep incomplete line in buffer

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') continue
      if (!payload) continue

      try {
        const ev = JSON.parse(payload)

        // Meta event carries session_id, not rendered
        if (ev.type === 'meta') {
          sessionId = ev.session_id ?? sessionId
          continue
        }

        // Apply minimum-reveal floor
        const floorMs = REVEAL_FLOOR[floorKeyForEvent(ev)] ?? 0
        const now = Date.now()
        const elapsed = now - lastRevealAt
        if (elapsed < floorMs) {
          await new Promise((r) => setTimeout(r, floorMs - elapsed))
        }
        lastRevealAt = Date.now()

        onEvent(ev as WorkshopEvent)
      } catch {
        // Skip malformed lines
      }
    }
  }

  return { session_id: sessionId }
}

/**
 * Non-streaming query — kept for backwards compatibility and tests.
 * Consumes the SSE stream internally and returns the buffered result.
 */
export async function queryWorkshop(
  req: WorkshopQueryRequest,
): Promise<WorkshopQueryResponse> {
  const events: WorkshopEvent[] = []
  const { session_id } = await queryWorkshopStream(req, (ev) => events.push(ev))
  return { session_id, events }
}

export interface WorkshopResumeRequest {
  customer_id: string
  session_id?: string | null
}

/**
 * Fires the "welcome-back" resume turn for a seeded demo customer.
 *
 * Emits three cohesive memory panels (EPISODIC / PREFERENCES /
 * PROCEDURAL) + a composed assistant text. The response shape
 * matches ``queryWorkshop`` so the chat column renders this as a
 * normal turn with ``user_text`` set to a pseudo-query in italics.
 */
export async function resumeWorkshop(
  req: WorkshopResumeRequest,
): Promise<WorkshopQueryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/atelier/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      customer_id: req.customer_id,
      session_id: req.session_id ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`workshop resume failed (${res.status}): ${body || res.statusText}`)
  }
  return (await res.json()) as WorkshopQueryResponse
}
