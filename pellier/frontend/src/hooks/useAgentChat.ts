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
  type ChatErrorCode,
  type ChatProduct,
} from '../services/chat'
import type { WorkshopMode } from '../contexts/LayoutContext'
import { usePersona } from '../contexts/PersonaContext'
import { readSkillMode } from '../components/turn/preferences'
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
export interface ReviewPending {
  /** What was opened. Internal; not shown to the shopper. */
  tool: string
  /** The durable request on the customer's case. */
  requestId?: number
  /** The customer whose record carries the request on the Operator desk. */
  customerId?: string
  message: string
}

export interface AgentChatMessage {
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
   * The governed boundary declined a mutation and a person has to confirm it.
   * Its own field rather than a sentence in `content`: the backend owns the
   * wording so a paraphrase cannot lose the guarantee.
   */
  reviewPending?: ReviewPending
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
    availability: p.availability,
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
function forStorage(messages: AgentChatMessage[]): AgentChatMessage[] {
  return messages.map(message => {
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
      return parsed.map(({ live: _live, ...msg }: any) => ({
        ...msg,
        timestamp: new Date(msg.timestamp),
      }))
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
  } = options

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
      turnAbortRef.current?.abort()
    }
  }, [])

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

      // CRITICAL: every updater below must be PURE. React 18 StrictMode
      // double-invokes state updaters in dev to surface impurity; any
      // mutation of `prev[i]` leaks across invocations and doubles additive
      // operations (content += delta). The last message is shallow-cloned
      // into a new object before writing.
      const updateLast = (
        patch: (msg: AgentChatMessage) => AgentChatMessage | null,
      ) => {
        setMessages(prev => {
          if (prev.length === 0) return prev
          const lastIdx = prev.length - 1
          const lastMsg = prev[lastIdx]
          if (lastMsg.role !== 'assistant') return prev
          const next = patch(lastMsg)
          if (next === null || next === lastMsg) return prev
          const updated = prev.slice()
          updated[lastIdx] = next
          return updated
        })
      }

      const loadingMessage: AgentChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        agentStatus: 'thinking',
        status: SENDING,
        steps: [],
        live: true,
      }
      setMessages(prev => [...prev, loadingMessage])

      const controller = new AbortController()
      turnAbortRef.current = controller

      try {
        const response = await sendChatMessageStreaming(
          text,
          historyBeforeUser,
          data => {
            // The hook unmounted mid-stream (see the mount effect above).
            if (!activeRef.current) return
            if (data.type === 'turn_start') {
              const principal = readPrincipal(data.principal)
              if (principal) updateLast(lastMsg => ({ ...lastMsg, principal }))
            } else if (data.type === 'status') {
              if (typeof data.label !== 'string') return
              updateLast(lastMsg => ({
                ...lastMsg,
                status: { label: data.label, state: 'working' },
              }))
            } else if (data.type === 'step') {
              const step: TurnStep = {
                id: String(data.id),
                label: String(data.label ?? ''),
                status: data.status === 'running' || data.status === 'failed' ? data.status : 'done',
                finding: typeof data.finding === 'string' ? data.finding : undefined,
                tags: Array.isArray(data.tags) ? data.tags.map(String) : [],
                builder: data.builder ?? undefined,
              }
              updateLast(lastMsg => ({
                ...lastMsg,
                steps: upsertStep(lastMsg.steps ?? [], step),
              }))
            } else if (data.type === 'content_delta') {
              const delta = typeof data.delta === 'string' ? data.delta : ''
              if (!delta) return
              updateLast(lastMsg => ({
                ...lastMsg,
                content: (lastMsg.content || '') + delta,
                agentStatus: 'streaming',
              }))
            } else if (data.type === 'content_reset') {
              updateLast(lastMsg => ({ ...lastMsg, content: '' }))
            } else if (data.type === 'content') {
              const content = typeof data.content === 'string' ? data.content : ''
              updateLast(lastMsg => {
                // The managed rail and the Router's fast paths answer in one
                // `content`. A streamed answer keeps its deltas when the
                // final text is only a shortened reading of them.
                if (
                  lastMsg.agentStatus === 'streaming' &&
                  lastMsg.content &&
                  (!content || content.length < lastMsg.content.length * 0.5)
                ) {
                  return lastMsg
                }
                return { ...lastMsg, content, agentStatus: 'streaming' }
              })
            } else if (data.type === 'product') {
              updateLast(lastMsg => {
                const existing = lastMsg.products ?? []
                const chatProduct = mapProduct(data.product)
                const isDupe = existing.some(
                  p =>
                    (p.id && p.id === chatProduct.id) ||
                    (p.name && p.name === chatProduct.name),
                )
                return {
                  ...lastMsg,
                  products: isDupe ? existing : [...existing, chatProduct],
                }
              })
            } else if (data.type === 'escalation') {
              updateLast(lastMsg => ({
                ...lastMsg,
                escalation: data.escalation as StylistHandoff,
              }))
            } else if (data.type === 'review_pending') {
              updateLast(lastMsg => ({
                ...lastMsg,
                reviewPending: data.reviewPending as ReviewPending,
              }))
            }
          },
          workshopMode,
          guardrailsEnabled,
          persona?.customer_id ?? null,
          controller.signal,
          readSkillMode(),
        )

        // Resolved after an unmount that fired mid-await. Nothing left to update.
        if (!activeRef.current) return

        if (response.estimated_cost_usd) {
          setSessionCost(prev => prev + response.estimated_cost_usd!)
        }

        updateLast(lastMsg => {
          // Prefer the streamed content over the complete event's parsed text
          // when the streamed version is substantially richer: the parser can
          // fall back to a generic line after stripping JSON blocks.
          let nextContent = lastMsg.content
          if (response.response) {
            const streamed = lastMsg.content || ''
            const final_ = response.response
            const streamedIsRicher =
              streamed.length > 80 && streamed.length > final_.length * 1.5
            if (!streamedIsRicher) {
              nextContent = final_
            }
          } else if (!lastMsg.content) {
            nextContent =
              "I couldn't land on a clear answer. Try rephrasing or narrowing the ask."
          }
          return {
            ...lastMsg,
            content: nextContent,
            products: response.products?.length
              ? response.products.map(mapProduct)
              : lastMsg.products,
            suggestions: response.suggestions,
            agentStatus: 'complete',
            status: lastMsg.status ? { ...lastMsg.status, state: 'done' } : undefined,
            failure: undefined,
            turnId: response.turn_id,
            sessionId: response.session_id,
            railDecision: response.railDecision,
            degradation: response.degradation,
          }
        })
        setBackendOnline(true)
      } catch (error) {
        // An unmount aborts `controller`, which surfaces here as a rejected
        // fetch. There is no drawer left to show a failure card in.
        if (!activeRef.current) return
        if (stoppedRef.current) {
          // The shopper pressed stop: what streamed is the answer so far.
          updateLast(lastMsg => ({
            ...lastMsg,
            agentStatus: 'complete',
            stopped: true,
            status: STOPPED,
            steps: (lastMsg.steps ?? []).filter(step => step.status !== 'running'),
          }))
          return
        }
        const chatError = normalizeChatError(error)
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
        if (activeRef.current) setIsLoading(false)
        sendingRef.current = false
      }
    },
    [inputValue, isLoading, workshopMode, guardrailsEnabled, persona?.customer_id],
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
