import { apiFetch } from '../services/apiBase'
/**
 * useAgentChat — the streaming chat state machine behind Ask Pellier.
 *
 * Owns the SSE event loop, the message array, the input value, loading and
 * backend state, and persistence. Every state the shopper sees comes from a
 * real stream event: the `status` line, the `step` list with its findings,
 * the text deltas, the products, the terminal `complete` or `error`. Nothing
 * is faked with timers. The reveal pacing is a rendering concern and lives
 * in `components/turn/RevealedProse`; this hook accumulates text as it
 * arrives.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { RailDecision, RailDegradation } from '../shared/governedTypes'
import {
  checkBackendHealth,
  normalizeChatError,
  sendChatMessageStreaming,
  watchTerminalTurns,
  type ChatErrorCode,
  type ChatProduct,
  type ChatResponse,
} from '../services/chat'
import type { WorkshopMode } from '../contexts/LayoutContext'
import { usePersona } from '../contexts/PersonaContext'
import { readSkillMode } from '../components/turn/preferences'
import { productsNamedInAnswer } from '../utils/answerCards'
import { upsertStep, type TurnPrincipal, type TurnStatus, type TurnStep } from '../components/turn/turnTypes'

/**
 * Stylist handoff payload from the `ask_a_person` tool.
 *
 * Emitted as a dedicated SSE event so the chat surface can render the
 * handoff card alongside the agent's prose. For the workshop it is a contact
 * card with a mailto fallback (pure UI, no real human on the other end).
 */
export interface StylistHandoff {
  channel: string
  status: string
  reason: string
  customer_id: string | null
  contact: {
    label: string
    mailto: string
    response_window: string
  }
  next_steps: string[]
}

export interface ChatFailure {
  code: ChatErrorCode
  retryable: boolean
  query: string
  referenceId?: string
}

/** A store credit request waiting for a person, as the backend states it. */
export interface CreditRequestPending {
  /** What was opened. Internal; not shown to the shopper. */
  tool: string
  /** The durable request on the customer's case. */
  requestId?: number
  /** The customer whose record carries the request on the Operator desk. */
  customerId?: string
  message: string
}

export interface AgentChatMessage {
  /** Names a typed turn's answer while it streams, so no other bubble takes its patches. */
  localId?: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  products?: ChatProduct[]
  suggestions?: string[]
  agentStatus?: 'thinking' | 'streaming' | 'complete'
  /** The status line, from the latest `status` event. */
  status?: TurnStatus
  /** The step list, merged by id from `step` events. */
  steps?: TurnStep[]
  /** The shopper pressed stop; the text on screen is all there is. */
  stopped?: boolean
  /**
   * Opened in this session, so its answer reveals as it arrives. False once
   * a newer turn opens, so an answer still revealing shows in full before
   * the next turn starts under it. Absent on a message loaded from storage
   * or hydrated from Memory, which shows at once.
   */
  live?: boolean
  /** Stylist handoff payload when this turn fired ask_a_person. */
  escalation?: StylistHandoff
  /** Recoverable transport or governance outcome for this turn. */
  failure?: ChatFailure
  /** Stable per-turn id from the backend, used to deep-link evidence. */
  turnId?: string
  /** Who the server verified for this turn, from `turn_start`. Builder evidence. */
  principal?: TurnPrincipal
  /** Session this turn belongs to, as reported by the backend. */
  sessionId?: string
  /** Which rail actually served the turn. */
  railDecision?: RailDecision
  /** Present only when the governed rail was requested and unavailable. */
  degradation?: RailDegradation
  /**
   * Sent from the terminal (`lab_run.py send`) and relayed to this panel, not
   * typed here. Relayed turns are not kept in the browser: the relay replays them.
   */
  source?: 'terminal'
  /**
   * The governed boundary declined a mutation and a person has to confirm it.
   * Its own field rather than a sentence in `content`: the backend owns the
   * wording so a paraphrase cannot lose the guarantee.
   */
  creditRequestPending?: CreditRequestPending
}

/**
 * What a turn reports to the page beside the dock, from the same stream
 * events: it started (with the shopper's words), its status changed, a step
 * arrived, it ended. The storefront's results grid follows these, so the page
 * and the answer read one stream.
 */
export type TurnEvent =
  | { type: 'start'; query: string }
  | { type: 'status'; label: string }
  | { type: 'step'; step: TurnStep }
  /** `picks` are the answer's cards, as Ask Pellier shows them, on a completed turn. */
  | { type: 'end'; outcome: 'complete' | 'failed' | 'stopped'; picks?: string[] }

/**
 * The ids of the cards Ask Pellier shows under an answer ("Pulled for you"),
 * in their order: the pieces the answer names that are new to the shopper,
 * and none when the answer is a request waiting on a person.
 */
export function answerPicks(message: AgentChatMessage): string[] {
  if (message.creditRequestPending) return []
  return productsNamedInAnswer(message.products ?? [], message.content)
    .filter(product => product.ownership !== 'owned')
    .map(product => String(product.id))
}

export interface UseAgentChatOptions {
  workshopMode?: WorkshopMode
  guardrailsEnabled?: boolean
  initialMessages?: AgentChatMessage[]
  /** localStorage key for conversation persistence. Omit to disable. */
  persistKey?: string
  /**
   * Session ID for AgentCore STM hydration. When provided, the hook fetches
   * `/api/agent/session/{sessionId}` on mount and hydrates the message list
   * from the backend's authoritative store if localStorage is empty.
   */
  sessionId?: string
  /** Hears each turn's start, status, steps and end. */
  onTurn?: (event: TurnEvent) => void
  /**
   * Show the turns the signed-in shopper sends from the terminal, relayed by
   * `/api/chat/watch`, beside the ones typed here.
   */
  watchTerminal?: boolean
}

export interface UseAgentChatReturn {
  messages: AgentChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<AgentChatMessage[]>>
  inputValue: string
  setInputValue: React.Dispatch<React.SetStateAction<string>>
  isLoading: boolean
  backendOnline: boolean
  sessionCost: number
  sendMessage: (customText?: string) => Promise<void>
  retryMessage: (text: string) => Promise<void>
  /** Stop the running turn; what has streamed stays on screen. */
  stopTurn: () => void
  clearChat: (resetTo?: AgentChatMessage[]) => void
}

const SENDING: TurnStatus = { label: 'Sending your request', state: 'working' }
const STOPPED: TurnStatus = { label: 'Stopped', state: 'done' }
const FAILED: TurnStatus = { label: 'Stopped before an answer', state: 'failed' }

function mapProduct(p: any): ChatProduct {
  return {
    id: p.id ?? p.productId ?? 0,
    name: p.name || p.product_description || '',
    price: p.price || 0,
    image: p.image || p.imgUrl || p.imgurl || p.image_url || '',
    category: p.category || p.category_name || '',
    rating: p.stars || p.rating || 0,
    reviews: p.reviews || 0,
    url: p.url || p.producturl || '',
    quantity: p.quantity,
    inStock: p.inStock,
    ownership:
      p.ownership === 'owned' || p.badge === 'From your orders'
        ? 'owned'
        : undefined,
    originalPrice: p.originalPrice,
    discountPercent: p.discountPercent,
    similarityScore:
      p.similarityScore ??
      p.similarity_score ??
      p.similarity ??
      p.relevance_score ??
      undefined,
  }
}

/**
 * What the conversation keeps in the browser. The identity binding on a
 * step and the turn's verified principal are Builder evidence for the turn
 * that ran them, not conversation state, so they never land in localStorage.
 *
 * By design, then, a turn restored after a reload carries no principal and
 * shows no identity line: the principal is shown only for turns that ran in
 * this page, from that turn's own `turn_start`. Restoring one from storage
 * would present a browser value as the server's verified identity.
 */
/** A `step` event as the panel holds it. */
export function toTurnStep(data: Record<string, any>): TurnStep {
  return {
    id: String(data.id),
    label: String(data.label ?? ''),
    status: data.status === 'running' || data.status === 'failed' ? data.status : 'done',
    finding: typeof data.finding === 'string' ? data.finding : undefined,
    tags: Array.isArray(data.tags) ? data.tags.map(String) : [],
    builder: data.builder ?? undefined,
    results: data.results && typeof data.results === 'object' ? data.results : undefined,
  }
}

/**
 * One stream event applied to the answer of the turn it belongs to, or null
 * when the event changes nothing there. A typed turn and a turn relayed from
 * the terminal both go through it, so both render the same way. Pure: React
 * StrictMode may call it twice.
 */
export function applyStreamEvent(
  msg: AgentChatMessage,
  data: Record<string, any>,
): AgentChatMessage | null {
  switch (data.type) {
    case 'turn_start': {
      const principal = readPrincipal(data.principal)
      // The turn id arrives here first, so a turn that fails or is refused
      // still names the key its evidence is filed under.
      const turnId = typeof data.turn_id === 'string' ? data.turn_id : undefined
      if (!principal && !turnId) return null
      return { ...msg, ...(principal ? { principal } : {}), ...(turnId ? { turnId } : {}) }
    }
    case 'status':
      if (typeof data.label !== 'string') return null
      return { ...msg, status: { label: data.label, state: 'working' } }
    case 'step':
      return { ...msg, steps: upsertStep(msg.steps ?? [], toTurnStep(data)) }
    case 'content_delta': {
      const delta = typeof data.delta === 'string' ? data.delta : ''
      if (!delta) return null
      return { ...msg, content: (msg.content || '') + delta, agentStatus: 'streaming' }
    }
    case 'content_reset':
      return { ...msg, content: '' }
    case 'content': {
      const content = typeof data.content === 'string' ? data.content : ''
      // The managed rail and the Router's fast paths answer in one `content`.
      // A streamed answer keeps its deltas when the final text is only a
      // shortened reading of them.
      if (
        msg.agentStatus === 'streaming' &&
        msg.content &&
        (!content || content.length < msg.content.length * 0.5)
      ) {
        return msg
      }
      return { ...msg, content, agentStatus: 'streaming' }
    }
    case 'product': {
      const existing = msg.products ?? []
      const chatProduct = mapProduct(data.product)
      const isDupe = existing.some(
        p => (p.id && p.id === chatProduct.id) || (p.name && p.name === chatProduct.name),
      )
      return { ...msg, products: isDupe ? existing : [...existing, chatProduct] }
    }
    case 'escalation':
      return { ...msg, escalation: data.escalation as StylistHandoff }
    case 'credit_request_pending':
      return { ...msg, creditRequestPending: data.creditRequestPending as CreditRequestPending }
    default:
      return null
  }
}

/** The answer once the turn's `complete` response has arrived. Pure. */
export function completeMessage(
  msg: AgentChatMessage,
  response: Pick<
    ChatResponse,
    'response' | 'products' | 'suggestions' | 'turn_id' | 'session_id' | 'railDecision' | 'degradation'
  >,
): AgentChatMessage {
  // Prefer the streamed content over the complete event's parsed text when
  // the streamed version is substantially richer: the parser can fall back to
  // a generic line after stripping JSON blocks.
  let nextContent = msg.content
  if (response.response) {
    const streamed = msg.content || ''
    const final_ = response.response
    const streamedIsRicher = streamed.length > 80 && streamed.length > final_.length * 1.5
    if (!streamedIsRicher) {
      nextContent = final_
    }
  } else if (!msg.content) {
    nextContent = "I couldn't land on a clear answer. Try rephrasing or narrowing the ask."
  }
  return {
    ...msg,
    content: nextContent,
    products: response.products?.length ? response.products.map(mapProduct) : msg.products,
    suggestions: response.suggestions,
    agentStatus: 'complete',
    status: msg.status ? { ...msg.status, state: 'done' } : undefined,
    failure: undefined,
    turnId: response.turn_id ?? msg.turnId,
    sessionId: response.session_id,
    railDecision: response.railDecision,
    degradation: response.degradation,
  }
}

let typedTurns = 0

function stoppedMessage(msg: AgentChatMessage): AgentChatMessage {
  return {
    ...msg,
    agentStatus: 'complete',
    stopped: true,
    status: STOPPED,
    steps: (msg.steps ?? []).filter(step => step.status !== 'running'),
  }
}

function forStorage(messages: AgentChatMessage[]): AgentChatMessage[] {
  return messages.filter(message => message.source !== 'terminal').map(({ localId: _localId, ...message }) => {
    const bound = message.steps?.some(step => step.builder?.identity)
    if (!bound && !message.principal) return message
    const { principal: _principal, ...kept } = message
    return {
      ...kept,
      steps: bound
        ? message.steps?.map(step =>
          step.builder?.identity ? { ...step, builder: { ...step.builder, identity: undefined } } : step,
        )
        : message.steps,
    }
  })
}

function readPrincipal(value: unknown): TurnPrincipal | undefined {
  if (!value || typeof value !== 'object') return undefined
  const raw = value as Record<string, unknown>
  const method = raw.signInMethod
  return {
    authenticated: raw.authenticated === true,
    customerId: typeof raw.customerId === 'string' ? raw.customerId : null,
    signInMethod: method === 'workshop' || method === 'cognito' ? method : null,
  }
}

/** Earlier answers are history once a new turn opens: any still revealing shows in full. */
function settled(messages: AgentChatMessage[]): AgentChatMessage[] {
  return messages.map(message =>
    message.role === 'assistant' && message.live ? { ...message, live: false } : message,
  )
}

function loadPersistedMessages(
  persistKey: string | undefined,
  fallback: AgentChatMessage[],
): AgentChatMessage[] {
  if (!persistKey) return fallback
  try {
    const saved = localStorage.getItem(persistKey)
    if (saved) {
      const parsed = JSON.parse(saved)
      return parsed.map(({ live: _live, localId: _localId, ...msg }: any) => {
        const cutOff = msg.role === 'assistant' && msg.agentStatus && msg.agentStatus !== 'complete'
        const restored = cutOff
          ? {
            ...msg,
            agentStatus: 'complete',
            status: FAILED,
            steps: (msg.steps ?? []).filter((step: { status?: string }) => step.status !== 'running'),
          }
          : msg
        return { ...restored, timestamp: new Date(msg.timestamp) }
      })
    }
  } catch {
    // ignore corrupted persistence
  }
  return fallback
}

export function useAgentChat(
  options: UseAgentChatOptions = {},
): UseAgentChatReturn {
  const {
    workshopMode,
    guardrailsEnabled = false,
    initialMessages = [],
    persistKey,
    sessionId,
    onTurn,
    watchTerminal = false,
  } = options

  // The listener can change between renders; the running turn reads the latest.
  const onTurnRef = useRef(onTurn)
  onTurnRef.current = onTurn
  const report = useCallback((event: TurnEvent) => onTurnRef.current?.(event), [])

  const [messages, setMessages] = useState<AgentChatMessage[]>(() =>
    loadPersistedMessages(persistKey, initialMessages),
  )
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [backendOnline, setBackendOnline] = useState(true)
  const [sessionCost, setSessionCost] = useState(0)

  // STM hydration: if the backend has turns that localStorage doesn't,
  // hydrate from the backend's AgentCore Memory (or in-memory fallback).
  useEffect(() => {
    if (!sessionId) return
    let alive = true
    apiFetch(`/api/agent/session/${encodeURIComponent(sessionId)}`)
      .then(r => r.json())
      .then(data => {
        if (!alive) return
        const turns = data?.turns
        if (!Array.isArray(turns) || turns.length === 0) return
        // Only hydrate if localStorage had nothing beyond the greeting.
        if (messages.length > 1) return
        const hydrated: AgentChatMessage[] = turns.map((t: { role?: string; content?: string; timestamp?: string }) => ({
          role: (t.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
          content: typeof t.content === 'string' ? t.content : '',
          timestamp: t.timestamp ? new Date(t.timestamp) : new Date(),
          agentStatus: 'complete' as const,
        }))
        setMessages(prev => {
          const greeting = prev.length > 0 ? [prev[0]] : initialMessages
          return [...greeting, ...hydrated]
        })
      })
      .catch(() => {
        // Silent: localStorage is the fallback
      })
    return () => { alive = false }
  }, [sessionId])

  // Active persona (if any): scopes backend profile reads to the right
  // customer_id. Read from context so persona switches take effect on the
  // next turn without remounting the chat surface.
  const { persona } = usePersona()

  // Keep a ref of the latest messages so sendMessage can read history
  // without re-creating the callback on every message update.
  const messagesRef = useRef(messages)
  // Synchronous guard against parallel sendMessage calls (React 18
  // StrictMode double-fires effects in dev mode).
  const sendingRef = useRef(false)
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // Whether this hook instance is still mounted, and the in-flight turn's
  // abort handle. `ShopperChatSlot` (App.tsx) unmounts ChatDrawer, and this
  // hook with it, on every navigation to /operator; without the guard a turn
  // kept streaming into a gone component.
  const activeRef = useRef(true)
  const turnAbortRef = useRef<AbortController | null>(null)
  const stoppedRef = useRef(false)
  useEffect(() => {
    activeRef.current = true
    return () => {
      activeRef.current = false
      // A turn cut off by leaving the storefront ends for the page too, so
      // its results view never waits on a stream nobody is reading.
      if (sendingRef.current) onTurnRef.current?.({ type: 'end', outcome: 'stopped' })
      turnAbortRef.current?.abort()
    }
  }, [])

  // A turn belongs to the shopper who asked it: choosing another shopper ends
  // it, so its stream cannot patch the new shopper's panel or block their send.
  const personaKey = persona?.id ?? null
  const seenPersonaKey = useRef(personaKey)
  const turnLocalIdRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (seenPersonaKey.current === personaKey) return
    seenPersonaKey.current = personaKey
    if (!sendingRef.current) return
    onTurnRef.current?.({ type: 'end', outcome: 'stopped' })
    turnAbortRef.current?.abort()
    turnAbortRef.current = null
    sendingRef.current = false
    setIsLoading(false)
    const ended = turnLocalIdRef.current
    setMessages(prev => prev.map(msg => (msg.localId === ended ? { ...stoppedMessage(msg), live: false } : msg)))
  }, [personaKey])

  // Turns the signed-in shopper sends from the terminal, relayed live beside
  // the ones typed here. One watch per shopper: a new shopper reconnects, and
  // a dropped stream (a backend restart) reconnects with backoff and replays
  // the recent turns, which reset and re-render rather than double.
  const watchedShopper = watchTerminal && persona && persona.id !== 'fresh' ? persona.id : null
  useEffect(() => {
    if (!watchedShopper) return
    const controller = new AbortController()
    let stopped = false
    let delayMs = 1000
    const replayed = new Set<string>()
    const started = new Set<string>()
    const updateRelayed = (
      turnId: string,
      patch: (msg: AgentChatMessage) => AgentChatMessage | null,
    ) => {
      setMessages(prev => {
        for (let i = prev.length - 1; i >= 0; i -= 1) {
          const msg = prev[i]
          if (msg.role !== 'assistant' || msg.source !== 'terminal' || msg.turnId !== turnId) continue
          const next = patch(msg)
          if (next === null || next === msg) return prev
          const updated = prev.slice()
          updated[i] = next
          return updated
        }
        return prev
      })
    }
    const onFrame = (frame: Record<string, any>) => {
      if (!activeRef.current) return
      delayMs = 1000
      const turnId = typeof frame.turn_id === 'string' ? frame.turn_id : ''
      if (!turnId) return
      if (frame.type === 'relay_turn') {
        const query = typeof frame.message === 'string' ? frame.message : ''
        const at = typeof frame.started_at === 'string' ? new Date(frame.started_at) : new Date()
        const fresh: AgentChatMessage = {
          role: 'assistant',
          content: '',
          timestamp: at,
          agentStatus: 'thinking',
          status: SENDING,
          steps: [],
          live: frame.replay !== true,
          source: 'terminal',
          turnId,
        }
        setMessages(prev => {
          const shown = prev.some(m => m.role === 'assistant' && m.source === 'terminal' && m.turnId === turnId)
          if (shown) {
            // A replay of a turn already on screen: start its answer over.
            return prev.map(m =>
              m.role === 'assistant' && m.source === 'terminal' && m.turnId === turnId ? fresh : m,
            )
          }
          return [
            ...settled(prev),
            { role: 'user', content: query, timestamp: at, source: 'terminal', turnId },
            fresh,
          ]
        })
        if (frame.replay === true) replayed.add(turnId)
        else replayed.delete(turnId)
        if (frame.replay !== true) {
          started.add(turnId)
          report({ type: 'start', query })
        }
      } else if (frame.type === 'relay_event') {
        const event = frame.event
        if (!event || typeof event !== 'object') return
        // A replayed turn rebuilds its bubble only; the results page already saw it.
        const reportable = !replayed.has(turnId) || started.has(turnId)
        if (reportable && event.type === 'status' && typeof event.label === 'string') {
          report({ type: 'status', label: event.label })
        } else if (reportable && event.type === 'step') {
          report({ type: 'step', step: toTurnStep(event) })
        }
        updateRelayed(turnId, msg =>
          event.type === 'complete'
            ? completeMessage(msg, event.response ?? {})
            : applyStreamEvent(msg, event),
        )
      } else if (frame.type === 'relay_end') {
        updateRelayed(turnId, msg =>
          msg.agentStatus === 'complete'
            ? null
            : {
              ...msg,
              agentStatus: 'complete',
              status: msg.status ? { ...msg.status, state: 'done' } : undefined,
              steps: (msg.steps ?? []).filter(step => step.status !== 'running'),
            },
        )
        if (!replayed.has(turnId) || started.has(turnId)) {
          report({ type: 'end', outcome: frame.outcome === 'error' ? 'failed' : 'complete' })
          started.delete(turnId)
        }
      }
    }
    const watch = async () => {
      while (!stopped) {
        try {
          await watchTerminalTurns(onFrame, controller.signal)
        } catch {
          // A dropped stream or a refused one: wait, then reconnect.
        }
        if (stopped) return
        await new Promise(resolve => setTimeout(resolve, delayMs))
        delayMs = Math.min(delayMs * 2, 10000)
      }
    }
    void watch()
    return () => {
      stopped = true
      controller.abort()
    }
  }, [watchedShopper, report])

  // Debounced persistence
  useEffect(() => {
    if (!persistKey) return
    const t = setTimeout(() => {
      try {
        localStorage.setItem(persistKey, JSON.stringify(forStorage(messages)))
      } catch {
        // quota exceeded: ignore
      }
    }, 500)
    return () => clearTimeout(t)
  }, [messages, persistKey])

  useEffect(() => {
    checkBackendHealth().then(setBackendOnline)
  }, [])

  const runMessage = useCallback(
    async (customText?: string, retrying = false) => {
      const text = (customText ?? inputValue).trim()
      if (!text || isLoading) return

      // Synchronous guard against double-invocation: two sendMessage calls
      // racing past the async isLoading check would open parallel streams
      // and interleave tokens into the same bubble.
      if (sendingRef.current) return
      sendingRef.current = true
      stoppedRef.current = false

      const userMessage: AgentChatMessage = {
        role: 'user',
        content: text,
        timestamp: new Date(),
      }
      let historyBeforeUser = messagesRef.current
      const lastMessage = historyBeforeUser.at(-1)
      const previousMessage = historyBeforeUser.at(-2)
      const canReuseUserTurn =
        retrying &&
        lastMessage?.role === 'assistant' &&
        lastMessage.failure?.query === text &&
        previousMessage?.role === 'user' &&
        previousMessage.content === text

      if (canReuseUserTurn) {
        const withoutFailure = historyBeforeUser.slice(0, -1)
        historyBeforeUser = withoutFailure.slice(0, -1)
        setMessages(settled(withoutFailure))
      } else {
        setMessages(prev => [...settled(prev), userMessage])
      }
      setInputValue('')
      setIsLoading(true)
      report({ type: 'start', query: text })

      const loadingMessage: AgentChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        agentStatus: 'thinking',
        status: SENDING,
        steps: [],
        live: true,
        localId: `typed-${(typedTurns += 1)}`,
      }
      // This turn's message as the panel will hold it, from the same patches,
      // so the turn's end can report the cards the panel shows.
      let answer = loadingMessage
      turnLocalIdRef.current = loadingMessage.localId
      // CRITICAL: every updater below must be PURE. React 18 StrictMode
      // double-invokes state updaters in dev to surface impurity; any
      // mutation of `prev[i]` leaks across invocations and doubles additive
      // operations (content += delta). The last message is shallow-cloned
      // into a new object before writing. Each patch also runs once on
      // `answer`, which purity makes safe.
      const updateLast = (
        patch: (msg: AgentChatMessage) => AgentChatMessage | null,
      ) => {
        answer = patch(answer) ?? answer
        setMessages(prev => {
          const index = prev.map(msg => msg.localId).lastIndexOf(loadingMessage.localId)
          if (index === -1) return prev
          const current = prev[index]
          const next = patch(current)
          if (next === null || next === current) return prev
          const updated = prev.slice()
          updated[index] = next
          return updated
        })
      }

      setMessages(prev => [...prev, loadingMessage])

      const controller = new AbortController()
      turnAbortRef.current = controller

      try {
        const response = await sendChatMessageStreaming(
          text,
          historyBeforeUser,
          data => {
            // The hook unmounted mid-stream (see the mount effect above), or
            // a new shopper ended this turn.
            if (!activeRef.current || turnAbortRef.current !== controller) return
            if (data.type === 'status' && typeof data.label === 'string') {
              report({ type: 'status', label: data.label })
            } else if (data.type === 'step') {
              report({ type: 'step', step: toTurnStep(data) })
            }
            updateLast(lastMsg => applyStreamEvent(lastMsg, data))
          },
          workshopMode,
          guardrailsEnabled,
          persona?.customer_id ?? null,
          controller.signal,
          readSkillMode(),
        )

        // Resolved after an unmount or a shopper change mid-await. Nothing left to update.
        if (!activeRef.current || turnAbortRef.current !== controller) return

        if (response.estimated_cost_usd) {
          setSessionCost(prev => prev + response.estimated_cost_usd!)
        }

        updateLast(lastMsg => completeMessage(lastMsg, response))
        setBackendOnline(true)
        report({ type: 'end', outcome: 'complete', picks: answerPicks(answer) })
      } catch (error) {
        // An unmount aborts `controller`, which surfaces here as a rejected
        // fetch. There is no drawer left to show a failure card in.
        if (!activeRef.current || turnAbortRef.current !== controller) return
        if (stoppedRef.current) {
          report({ type: 'end', outcome: 'stopped' })
          // The shopper pressed stop: what streamed is the answer so far.
          updateLast(stoppedMessage)
          return
        }
        const chatError = normalizeChatError(error)
        report({ type: 'end', outcome: 'failed' })
        updateLast(lastMsg => ({
          ...lastMsg,
          content: '',
          agentStatus: 'complete',
          status: FAILED,
          products: undefined,
          suggestions: undefined,
          failure: {
            code: chatError.code,
            retryable: chatError.retryable,
            query: text,
            referenceId: chatError.referenceId,
          },
        }))
        setBackendOnline(
          !['network_error', 'service_unavailable'].includes(chatError.code),
        )
      } finally {
        if (turnAbortRef.current === controller) {
          turnLocalIdRef.current = undefined
          if (activeRef.current) setIsLoading(false)
          sendingRef.current = false
        }
      }
    },
    [inputValue, isLoading, workshopMode, guardrailsEnabled, persona?.customer_id, report],
  )

  const sendMessage = useCallback(
    (customText?: string) => runMessage(customText, false),
    [runMessage],
  )

  const retryMessage = useCallback(
    (text: string) => runMessage(text, true),
    [runMessage],
  )

  const stopTurn = useCallback(() => {
    if (!turnAbortRef.current) return
    stoppedRef.current = true
    turnAbortRef.current.abort()
  }, [])

  const clearChat = useCallback(
    (resetTo?: AgentChatMessage[]) => {
      if (persistKey) {
        localStorage.removeItem(persistKey)
        // Do NOT remove 'pellier-session-id' here: PersonaContext owns the
        // backend session-id lifecycle.
      }
      setMessages(resetTo ?? initialMessages)
    },
    [persistKey, initialMessages],
  )

  return {
    messages,
    setMessages,
    inputValue,
    setInputValue,
    isLoading,
    backendOnline,
    sessionCost,
    sendMessage,
    retryMessage,
    stopTurn,
    clearChat,
  }
}
