/**
 * useAgentChat — streaming chat state machine shared by ConciergeModal and
 * (transitionally) AIAssistant. Owns the SSE event loop, message array,
 * input value, loading/backend/session-cost state, and persistence.
 *
 * Rendering concerns (scroll, animations, badge layout, Under the Hood
 * block) stay in the component; the hook only produces well-shaped
 * AgentChatMessage objects with all metadata populated.
 *
 * `mode` switches high-level behavior:
 *   - 'storefront' — no agent inference, no agent badges, plain chat
 *   - 'atelier'    — populate agent/agentExecution so instrumentation UI
 *                    (badges, Under the Hood) can render
 *
 * `workshopMode` and `guardrailsEnabled` are passed through to the
 * streaming endpoint so backend routing (legacy/search/agentic/production)
 * works identically to the old AIAssistant flow.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  checkBackendHealth,
  sendChatMessageStreaming,
  type ChatProduct,
} from '../services/chat'
import type { WorkshopMode } from '../contexts/LayoutContext'
import { usePersona } from '../contexts/PersonaContext'

export type ChatMode = 'storefront' | 'atelier'

export interface AgentStep {
  agent: string
  action: string
  status: string
  timestamp: number
  duration_ms: number
}

export interface ToolCall {
  tool: string
  params?: string
  timestamp: number
  duration_ms: number
  status: string
}

export interface AgentExecution {
  agent_steps: AgentStep[]
  tool_calls: ToolCall[]
  reasoning_steps: Array<{ step: string; content: string; timestamp: number }>
  total_duration_ms: number
  success_rate: number
  /** False when Strands' TracerProvider isn't SDK-backed. UI shows a
   * banner and suppresses the waterfall when this is explicitly false. */
  otel_enabled?: boolean
  /** Actionable failure string from the backend when otel_enabled is
   * false. Rendered verbatim in the banner. */
  reason?: string
}

/**
 * Skill routing decision for one turn.
 *
 * Shape mirrors the backend ``RouterDecision`` Pydantic model. Emitted
 * once per turn via the ``skill_routing`` SSE event, before any text
 * tokens, so the storefront can render the attribution line above the
 * reply and the Atelier can render the live activation log.
 */
export interface SkillRouting {
  loaded_skills: string[]
  considered: Array<{ name: string; reason: string }>
  elapsed_ms: number
  raw_response?: string
  user_message: string
}

/**
 * Stylist handoff payload from the `escalate_to_stylist` tool.
 *
 * Emitted as a dedicated SSE event so the chat surface can render the
 * handoff card alongside the agent's prose. The "stylist" is the
 * placeholder name for the human escalation channel — production
 * deployments wire it to live chat or a CX queue. For the workshop
 * it's a contact card with a mailto fallback (pure UI, no real human
 * on the other end).
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

export type AgentBadge =
  | 'search'
  | 'pricing'
  | 'recommendation'
  | 'orchestrator'
  | 'inventory'
  | 'support'

export interface AgentChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  products?: ChatProduct[]
  suggestions?: string[]
  agent?: AgentBadge
  agentStatus?: 'thinking' | 'streaming' | 'complete'
  agentExecution?: AgentExecution
  /** Skill routing decision for this turn. Set when the backend emits
   * a ``skill_routing`` SSE event. Boutique uses ``loaded_skills`` to
   * render the italic burgundy attribution line; Atelier renders the
   * full decision in its live activation log. */
  skillRouting?: SkillRouting
  /** Stylist handoff payload when this turn fired escalate_to_stylist.
   * The chat surface renders the StylistHandoffCard in place of the
   * usual product grid. */
  escalation?: StylistHandoff
}

export interface UseAgentChatOptions {
  mode?: ChatMode
  workshopMode?: WorkshopMode
  guardrailsEnabled?: boolean
  initialMessages?: AgentChatMessage[]
  /** localStorage key for conversation persistence. Omit to disable. */
  persistKey?: string
  /**
   * Session ID for AgentCore STM hydration. When provided, the hook
   * fetches `/api/agent/session/{sessionId}` on mount and hydrates
   * the message list from the backend's authoritative STM store if
   * localStorage is empty or stale. This bridges the Boutique chat
   * with the same STM layer the Atelier teaches.
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
  clearChat: (resetTo?: AgentChatMessage[]) => void
}

const CACHE_TTL = 5 * 60 * 1000
const responseCache = new Map<
  string,
  {
    response: string
    products?: ChatProduct[]
    suggestions?: string[]
    agent: AgentBadge
    timestamp: number
  }
>()

function cacheKey(query: string) {
  return query.trim().toLowerCase()
}

function getCachedResponse(query: string) {
  const cached = responseCache.get(cacheKey(query))
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) return cached
  return null
}

function setCachedResponse(
  query: string,
  data: {
    response: string
    products?: ChatProduct[]
    suggestions?: string[]
    agent: AgentBadge
  },
) {
  responseCache.set(cacheKey(query), { ...data, timestamp: Date.now() })
}

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

function inferAgentFromQuery(q: string): AgentBadge {
  const lower = q.toLowerCase()
  if (
    lower.includes('return') ||
    lower.includes('refund') ||
    lower.includes('policy') ||
    lower.includes('support') ||
    lower.includes('warranty') ||
    lower.includes('help')
  ) return 'support'
  if (
    lower.includes('cheap') ||
    lower.includes('price') ||
    lower.includes('deal') ||
    lower.includes('cost') ||
    lower.includes('budget') ||
    lower.includes('afford')
  ) return 'pricing'
  if (
    lower.includes('recommend') ||
    lower.includes('suggest') ||
    lower.includes('best') ||
    lower.includes('top') ||
    lower.includes('popular') ||
    lower.includes('trending')
  ) return 'recommendation'
  return 'search'
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
      return parsed.map((msg: any) => ({
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
    mode = 'storefront',
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

  // STM hydration — fetch the authoritative turn history from the
  // backend's AgentCore Memory (or in-memory fallback). If the backend
  // has turns that localStorage doesn't, hydrate from backend. This
  // bridges the Boutique chat with the STM the Atelier teaches.
  useEffect(() => {
    if (!sessionId) return
    let alive = true
    fetch(`/api/agent/session/${encodeURIComponent(sessionId)}`)
      .then(r => r.json())
      .then(data => {
        if (!alive) return
        const turns = data?.turns
        if (!Array.isArray(turns) || turns.length === 0) return
        // Only hydrate if localStorage had nothing beyond the greeting
        // (≤1 message = just the initial greeting, no real turns)
        if (messages.length > 1) return
        const hydrated: AgentChatMessage[] = turns.map((t: { role?: string; content?: string; timestamp?: string }) => ({
          role: (t.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
          content: typeof t.content === 'string' ? t.content : '',
          timestamp: t.timestamp ? new Date(t.timestamp) : new Date(),
        }))
        setMessages(prev => {
          // Keep the greeting (first message) + append backend turns
          const greeting = prev.length > 0 ? [prev[0]] : initialMessages
          return [...greeting, ...hydrated]
        })
      })
      .catch(() => {
        // Silent — localStorage is the fallback
      })
    return () => { alive = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps — only on sessionId change
  }, [sessionId])

  // Active persona (if any) — used to scope backend LTM reads to the
  // right customer_id. Read from context so persona switches take
  // effect on the next turn without remounting the chat surface.
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

  // Debounced persistence
  useEffect(() => {
    if (!persistKey) return
    const t = setTimeout(() => {
      try {
        localStorage.setItem(persistKey, JSON.stringify(messages))
      } catch {
        // quota exceeded — drop oldest? For now, ignore
      }
    }, 500)
    return () => clearTimeout(t)
  }, [messages, persistKey])

  useEffect(() => {
    checkBackendHealth().then(setBackendOnline)
  }, [])

  const sendMessage = useCallback(
    async (customText?: string) => {
      const text = (customText ?? inputValue).trim()
      if (!text || isLoading) return

      // Synchronous guard against double-invocation. React 18
      // StrictMode double-fires effects in dev mode; if two
      // sendMessage calls race past the isLoading state check
      // (which is async), they'd open parallel SSE streams and
      // interleave tokens into the same message bubble. The ref
      // is set synchronously so the second call always sees it.
      if (sendingRef.current) return
      sendingRef.current = true

      const userMessage: AgentChatMessage = {
        role: 'user',
        content: text,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, userMessage])
      setInputValue('')
      setIsLoading(true)

      // Streaming delta buffer + rAF flush.
      //
      // Streaming text handling — direct state update per delta.
      //
      // Previous approach used a requestAnimationFrame buffer to batch
      // deltas at 60fps. This caused a persistent "stuttering" bug
      // where pre-tool tokens leaked through content_reset boundaries
      // via stale rAF callbacks. The direct approach is simpler and
      // React 18's automatic batching already coalesces rapid
      // setState calls within the same microtask, so the render
      // frequency is naturally throttled.
      //
      // CRITICAL: every updater below must be PURE. React 18 StrictMode
      // double-invokes state updaters in dev to surface impurity — any
      // mutation of `prev[i]` leaks across invocations and doubles
      // additive operations (content += delta). We shallow-clone the
      // last message into a new object before writing, so the second
      // StrictMode invocation re-reads the original `prev` state and
      // produces the same output.
      const updateLast = (
        patch: (msg: AgentChatMessage) => AgentChatMessage | null,
      ) => {
        setMessages(prev => {
          if (prev.length === 0) return prev
          const lastIdx = prev.length - 1
          const lastMsg = prev[lastIdx]
          const next = patch(lastMsg)
          if (next === null || next === lastMsg) return prev
          const updated = prev.slice()
          updated[lastIdx] = next
          return updated
        })
      }

      const appendDelta = (delta: string) => {
        updateLast(lastMsg => {
          if (lastMsg.role !== 'assistant') return null
          return {
            ...lastMsg,
            content: (lastMsg.content || '') + delta,
            agentStatus:
              lastMsg.agentStatus === 'thinking'
                ? 'streaming'
                : lastMsg.agentStatus,
            agentExecution:
              lastMsg.agentStatus === 'thinking'
                ? undefined
                : lastMsg.agentExecution,
          }
        })
      }

      // Cache check
      const cached = getCachedResponse(text)
      if (cached) {
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: cached.response,
            timestamp: new Date(),
            products: cached.products,
            suggestions: cached.suggestions,
            agent: cached.agent,
            agentStatus: 'complete',
          },
        ])
        setIsLoading(false)
        sendingRef.current = false
        return
      }

      // Thinking placeholder. Atelier gets the full instrumentation shell;
      // storefront gets a lightweight shell so Boutique can show an optional
      // collapsed "skills + tools" disclosure without surfacing agent steps.
      const showInstrumentation = mode === 'atelier'
      const trackToolCalls = showInstrumentation || mode === 'storefront'
      const thinkingAgentName =
        workshopMode === 'production'
          ? 'AgentCore'
          : workshopMode === 'agentic'
            ? 'Orchestrator'
            : 'Style Advisor'
      const loadingMessage: AgentChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        agentStatus: 'thinking',
        agent: showInstrumentation
          ? workshopMode === 'agentic' || workshopMode === 'production'
            ? 'orchestrator'
            : 'search'
          : undefined,
        agentExecution: trackToolCalls
          ? {
              agent_steps: showInstrumentation
                ? [
                    {
                      agent: thinkingAgentName,
                      action: 'Analyzing query',
                      status: 'in_progress',
                      timestamp: Date.now(),
                      duration_ms: 0,
                    },
                  ]
                : [],
              tool_calls: [],
              reasoning_steps: [],
              total_duration_ms: 0,
              success_rate: 0,
            }
          : undefined,
      }
      setMessages(prev => [...prev, loadingMessage])

      try {
        const historyBeforeUser = messagesRef.current

        const response = await sendChatMessageStreaming(
          text,
          historyBeforeUser,
          data => {
            if (data.type === 'skill_routing') {
              // Routing event arrives BEFORE any text tokens per the
              // backend ordering contract. Attach to the current
              // assistant message (the thinking placeholder) so both
              // the storefront attribution line and the Atelier
              // activation log can read it.
              updateLast(lastMsg =>
                lastMsg.role === 'assistant'
                  ? { ...lastMsg, skillRouting: data.routing }
                  : null,
              )
              // Persist the most recent routing to localStorage so the
              // Atelier Skills panel (which lives on a different route)
              // can render the live activation log without plumbing
              // cross-route state through a context provider.
              try {
                localStorage.setItem(
                  'pellier-skill-routing-latest',
                  JSON.stringify(data.routing),
                )
              } catch {
                // quota or private mode — silent
              }
            } else if (data.type === 'agent_step') {
              if (!showInstrumentation) return
              updateLast(lastMsg => {
                if (
                  lastMsg.agentStatus !== 'thinking' ||
                  !lastMsg.agentExecution
                ) {
                  return null
                }
                const existingIdx = lastMsg.agentExecution.agent_steps.findIndex(
                  s => s.agent === data.agent,
                )
                let nextSteps
                if (existingIdx >= 0) {
                  nextSteps = lastMsg.agentExecution.agent_steps.map((s, i) =>
                    i === existingIdx ? { ...s, status: data.status } : s,
                  )
                } else {
                  nextSteps = [
                    ...lastMsg.agentExecution.agent_steps,
                    {
                      agent: data.agent,
                      action: data.action,
                      status: data.status,
                      timestamp: Date.now(),
                      duration_ms: 0,
                    },
                  ]
                }
                return {
                  ...lastMsg,
                  agentExecution: {
                    ...lastMsg.agentExecution,
                    agent_steps: nextSteps,
                  },
                }
              })
            } else if (data.type === 'tool_call') {
              // Always persist tool calls to localStorage so the
              // Atelier architecture pages (MCP, Tool Registry) can
              // render the live strip without being mounted in the
              // same component tree as the chat. Cross-route state.
              try {
                const raw = localStorage.getItem('pellier-last-tool-calls')
                const prev = raw ? JSON.parse(raw) : []
                const list = Array.isArray(prev) ? prev : []
                list.push({
                  tool: data.tool,
                  args: data.args,
                  agent: data.agent,
                  duration_ms: data.duration_ms ?? 0,
                  timestamp: Date.now(),
                })
                // Keep last 20 calls across turns — enough for demos.
                const trimmed = list.slice(-20)
                localStorage.setItem(
                  'pellier-last-tool-calls',
                  JSON.stringify(trimmed),
                )
              } catch {
                // quota / private mode — non-fatal
              }
              if (!trackToolCalls) return
              updateLast(lastMsg => {
                if (
                  lastMsg.agentStatus !== 'thinking' ||
                  !lastMsg.agentExecution
                ) {
                  return null
                }
                return {
                  ...lastMsg,
                  agentExecution: {
                    ...lastMsg.agentExecution,
                    tool_calls: [
                      ...lastMsg.agentExecution.tool_calls,
                      {
                        tool: data.tool,
                        timestamp: Date.now(),
                        duration_ms: data.duration_ms ?? 0,
                        status: data.status,
                      },
                    ],
                  },
                }
              })
            } else if (data.type === 'content_delta') {
              // Diagnostic: log every delta received for stuttering investigation
              if (typeof window !== 'undefined' && (window as any).__PELLIER_DEBUG_DELTAS) {
                console.log(`[delta] ${JSON.stringify(data.delta).slice(0, 40)}`)
              }
              appendDelta(data.delta)
            } else if (data.type === 'content_reset') {
              // Clear the bubble for Pattern I's post-tool response.
              // Pattern III (dispatcher) skips this event server-side.
              updateLast(lastMsg => ({
                ...lastMsg,
                content: '',
                agentStatus:
                  lastMsg.agentStatus === 'streaming'
                    ? 'thinking'
                    : lastMsg.agentStatus,
              }))
            } else if (data.type === 'content') {
              updateLast(lastMsg => {
                if (
                  lastMsg.agentStatus === 'streaming' &&
                  lastMsg.content &&
                  (!data.content ||
                    data.content.length < lastMsg.content.length * 0.5)
                ) {
                  return {
                    ...lastMsg,
                    agentStatus: 'complete',
                    agentExecution: showInstrumentation ? undefined : lastMsg.agentExecution,
                  }
                }
                return {
                  ...lastMsg,
                  content: data.content,
                  agentStatus: 'complete',
                  agentExecution: showInstrumentation ? undefined : lastMsg.agentExecution,
                }
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
                  agentStatus: 'complete',
                  agentExecution: showInstrumentation ? undefined : lastMsg.agentExecution,
                }
              })
            } else if (data.type === 'runtime_timing') {
              // Per-layer wall-clock timing for the most recent turn.
              // Written to localStorage for the Atelier Runtime page
              // to consume via useRuntimeTiming().
              try {
                localStorage.setItem(
                  'pellier-last-runtime-timing',
                  JSON.stringify(data.timing),
                )
              } catch {
                // quota / private mode — non-fatal
              }
            } else if (data.type === 'escalation') {
              // Honest "this is outside what I can answer" handoff.
              // Render the StylistHandoffCard in place of product
              // cards via message.escalation; the agent's prose stays
              // alongside it.
              updateLast(lastMsg => {
                if (lastMsg.role !== 'assistant') return null
                return {
                  ...lastMsg,
                  escalation: data.escalation as StylistHandoff,
                  agentStatus: 'complete',
                }
              })
            } else if (data.type === 'db_queries') {
              // Per-turn database operations (reads and writes) with
              // SQL snippets. Written to localStorage for the Atelier
              // State Management page to consume via useDbQueries().
              try {
                const list = Array.isArray(data.queries) ? data.queries : []
                localStorage.setItem(
                  'pellier-last-db-queries',
                  JSON.stringify(list),
                )
              } catch {
                // quota / private mode — non-fatal
              }
            }
          },
          // Boutique mode always gets full chat access regardless of
          // which workshop module the participant has completed.
          mode === 'storefront' ? undefined : workshopMode,
          guardrailsEnabled,
          persona?.customer_id ?? null,
          // Pattern selector — storefront uses the dispatcher (direct
          // specialist invocation, no orchestrator, no paraphrase),
          // atelier uses the Haiku orchestrator (Pattern I). Commit 2
          // adds a user-facing toggle in the Atelier for 'graph'.
          mode === 'storefront' ? 'dispatcher' : 'agents_as_tools',
        )

        if (response.estimated_cost_usd) {
          setSessionCost(prev => prev + response.estimated_cost_usd!)
        }

        // Determine agent badge — only when instrumentation is on
        let agentType: AgentBadge | undefined
        if (showInstrumentation) {
          if (
            workshopMode === 'agentic' ||
            workshopMode === 'production' ||
            response.orchestrator_enabled
          ) {
            agentType = 'orchestrator'
          } else {
            agentType = inferAgentFromQuery(text)
          }
        }

        updateLast(lastMsg => {
          // Prefer the streamed content (built from content_delta events)
          // over the complete event's response.response when the streamed
          // version is substantially richer. The backend's
          // _parse_agent_response sometimes produces a generic fallback
          // ("Here are some great options!") when it strips JSON blocks
          // from the AgentResult — but the specialist's actual prose was
          // already streamed to the bubble via content_delta.
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
              "I couldn't land on a clear answer — try rephrasing or narrowing the ask."
          }
          return {
            ...lastMsg,
            content: nextContent,
            products: response.products?.length
              ? response.products.map(mapProduct)
              : lastMsg.products,
            suggestions: response.suggestions,
            agent: agentType,
            agentStatus: 'complete',
            agentExecution: showInstrumentation
              ? response.agent_execution
              : response.agent_execution
                ? {
                    ...response.agent_execution,
                    agent_steps: [],
                    reasoning_steps: [],
                  }
                : lastMsg.agentExecution,
          }
        })
        setBackendOnline(true)

        if (agentType) {
          setCachedResponse(text, {
            response: response.response,
            products: response.products,
            suggestions: response.suggestions,
            agent: agentType,
          })
        } else {
          setCachedResponse(text, {
            response: response.response,
            products: response.products,
            suggestions: response.suggestions,
            agent: 'search',
          })
        }
      } catch {
        updateLast(lastMsg => ({
          ...lastMsg,
          content:
            'Unable to connect. Please check that the backend is running.',
          agentStatus: 'complete',
          agentExecution: undefined,
        }))
        setBackendOnline(false)
      } finally {
        setIsLoading(false)
        sendingRef.current = false
      }
    },
    [inputValue, isLoading, mode, workshopMode, guardrailsEnabled, persona?.customer_id],
  )

  const clearChat = useCallback(
    (resetTo?: AgentChatMessage[]) => {
      if (persistKey) {
        localStorage.removeItem(persistKey)
        localStorage.removeItem('pellier-session-id')
      }
      responseCache.clear()
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
    clearChat,
  }
}
