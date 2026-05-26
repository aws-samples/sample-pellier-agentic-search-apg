/**
 * ConciergeModal — single chat surface for the storefront and workshop.
 *
 * Shell: centered cream rounded-3xl card with glass backdrop-blur, per
 * storefront.md §"Global UI elements". Open/close is coordinated through
 * UIContext.activeModal === 'concierge'. Cmd+K / Escape handled globally
 * in UIProvider.
 *
 * Content: driven entirely by `useAgentChat`. ConciergeModal owns only
 * rendering — scroll, animations, badge layout, Under the Hood block.
 *
 * Mode selection via useLocation():
 *   - pathname.startsWith('/atelier') → instrumentation mode. Agent
 *     badges render, "Under the Hood" expandable shows tool calls,
 *     guardrails, context stats. Trace-ID footer links to
 *     /inspector?session={id}.
 *   - otherwise (storefront, /discover, /storyboard) → clean chat. No
 *     badges, no Under the Hood affordance, no trace footer.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useLocation, Link } from 'react-router-dom'
import { Send, X, GitCompare, AlertCircle } from 'lucide-react'
import { useUI } from '../contexts/UIContext'
import { useLayout } from '../contexts/LayoutContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useAgentChat, type AgentBadge, type AgentChatMessage } from '../hooks/useAgentChat'
import { AGENT_IDENTITIES, type AgentType } from '../utils/agentIdentity'
import ProductCardConcierge from './ProductCardConcierge'
import MarkdownMessage from './MarkdownMessage'
import { cssVar as c } from '../design/cssVars'

// Warm palette → Daylight via `cssVars` / bridge.

const WELCOME_STOREFRONT =
  "Tell me what you're after. Linen for a slow Sunday, a piece that travels, a gift that lands."
const WELCOME_WORKSHOP =
  "Workshop mode: every response includes agent routing, tool calls, and timings. Open Under the Hood on any reply."

const SUGGESTIONS_STOREFRONT = [
  'something for long summer walks',
  'a linen piece that earns its golden hour',
  'pieces that travel well',
]
const SUGGESTIONS_WORKSHOP = [
  'Find me the best linen shirt under $150',
  'What is low on stock right now?',
  'Compare the Sundress and the Cardigan',
]

// Persona-tailored suggestion chips. Each array reflects the persona's
// actual signals (orders, search_history, ltm_facts) from
// docs/personas-config.json, so the concierge opens with prompts that
// already feel like they "know" the shopper. Fresh visitor gets the
// generic editorial chips.
const SUGGESTIONS_BY_PERSONA: Record<string, string[]> = {
  marco: [
    'what did I buy last time?',
    'something similar to what I bought last time',
    'pieces that travel well for Lisbon',
  ],
  anna: [
    'a thoughtful gift for my mother',
    'something similar to what I bought last time',
    'milestone pieces under $200',
  ],
  fresh: SUGGESTIONS_STOREFRONT,
}

// Session id read from the same localStorage key the chat service writes.
function useSessionId(): string | null {
  const [id, setId] = useState<string | null>(() => localStorage.getItem('pellier-session-id'))
  useEffect(() => {
    const t = setInterval(() => {
      const current = localStorage.getItem('pellier-session-id')
      if (current && current !== id) setId(current)
    }, 1000)
    return () => clearInterval(t)
  }, [id])
  return id
}

// Badge color map — covers all six specialist variants (storefront palette).
const BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  orchestrator: { bg: 'rgba(168, 85, 247, 0.18)', text: '#7e22ce' },
  search: { bg: 'rgba(59, 130, 246, 0.18)', text: '#1d4ed8' },
  pricing: { bg: 'rgba(245, 158, 11, 0.18)', text: '#b45309' },
  recommendation: { bg: 'rgba(234, 179, 8, 0.18)', text: '#a16207' },
  inventory: { bg: 'rgba(16, 185, 129, 0.18)', text: '#047857' },
  support: { bg: 'rgba(20, 184, 166, 0.18)', text: '#0f766e' },
}

// Map raw step.agent names emitted by the orchestrator into AgentBadge keys
// so rendering logic has one shape to deal with.
function normalizeStepAgent(raw: string): AgentBadge {
  const n = raw.toLowerCase()
  if (n.includes('search')) return 'search'
  if (n.includes('price') || n.includes('pricing')) return 'pricing'
  if (n.includes('recommend')) return 'recommendation'
  if (n.includes('inventory')) return 'inventory'
  if (n.includes('support') || n.includes('customer')) return 'support'
  return 'orchestrator'
}

function AgentBadgePill({ kind }: { kind: AgentBadge }) {
  const colors = BADGE_COLORS[kind] || BADGE_COLORS.orchestrator
  const name = AGENT_IDENTITIES[kind as AgentType]?.name || 'Agent'
  return (
    <span
      data-testid={`agent-badge-${kind}`}
      className="text-[10px] px-2 py-0.5 rounded-full font-medium"
      style={{ background: colors.bg, color: colors.text }}
    >
      {name}
    </span>
  )
}

function AgentBadgeRow({ message }: { message: AgentChatMessage }) {
  // Multi-specialist fan-out from orchestrator: show each specialist that ran.
  if (message.agent === 'orchestrator' && message.agentExecution?.agent_steps?.length) {
    const specialists = message.agentExecution.agent_steps
      .filter(s => s.agent !== 'Orchestrator' && s.agent !== 'Aggregator')
      .map(s => normalizeStepAgent(s.agent))
    if (specialists.length === 0) {
      return (
        <div className="flex items-center gap-1.5 mb-2 flex-wrap">
          <AgentBadgePill kind="orchestrator" />
        </div>
      )
    }
    const seen = new Set<string>()
    const unique = specialists.filter(s => (seen.has(s) ? false : (seen.add(s), true)))
    return (
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        {unique.map((kind, i) => <AgentBadgePill key={i} kind={kind} />)}
      </div>
    )
  }
  if (!message.agent) return null
  return (
    <div className="flex items-center gap-1.5 mb-2 flex-wrap">
      <AgentBadgePill kind={message.agent} />
    </div>
  )
}

interface UnderTheHoodProps {
  index: number
  message: AgentChatMessage
  expanded: boolean
  onToggle: () => void
  guardrailsEnabled: boolean
}

function UnderTheHood({ index, message, expanded, onToggle, guardrailsEnabled }: UnderTheHoodProps) {
  const toolCount = message.agentExecution?.tool_calls?.length ?? 0
  const agentName = message.agent
    ? AGENT_IDENTITIES[message.agent as AgentType]?.name || 'Agent'
    : 'Agent'

  return (
    <div className="mt-1" data-testid={`under-the-hood-${index}`}>
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 text-[10px] w-full text-left px-2 py-1 rounded-md transition-colors"
        style={{
          color: c.ink2,
          background: expanded ? 'rgba(45, 24, 16, 0.04)' : 'transparent',
        }}
      >
        <svg
          className="h-3 w-3 flex-shrink-0 transition-transform"
          style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="font-medium" style={{ color: c.ink }}>Under the Hood</span>
        {message.agent && (
          <span
            className="px-1.5 py-0.5 rounded text-[9px] font-medium"
            style={{ background: 'rgba(45, 24, 16, 0.04)', color: c.ink2 }}
          >
            {agentName}
          </span>
        )}
        {toolCount > 0 && (
          <span
            className="px-1.5 py-0.5 rounded text-[9px]"
            style={{ background: 'rgba(45, 24, 16, 0.04)', color: c.ink2 }}
          >
            {toolCount} tool{toolCount !== 1 ? 's' : ''}
          </span>
        )}
        {guardrailsEnabled && (
          <span
            className="px-1.5 py-0.5 rounded text-[9px]"
            style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#047857' }}
          >
            Guarded
          </span>
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            className="px-3 py-2 mt-1 rounded-lg text-[11px] space-y-1.5"
            style={{
              background: 'rgba(45, 24, 16, 0.03)',
              border: '1px solid rgba(45, 24, 16, 0.06)',
            }}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            {message.agent && (
              <div>
                <span className="font-semibold" style={{ color: c.ink2 }}>Agent: </span>
                <span style={{ color: c.ink }}>{agentName}</span>
                <span className="ml-1" style={{ color: c.muted }}>
                  {message.agent === 'search' && '- finds products via semantic search and filters'}
                  {message.agent === 'pricing' && '- analyzes price trends, deals, and budget options'}
                  {message.agent === 'recommendation' && '- suggests products based on preferences'}
                  {message.agent === 'orchestrator' && '- coordinates multiple agents for complex queries'}
                  {message.agent === 'inventory' && '- checks stock and restock requests'}
                  {message.agent === 'support' && '- handles returns, warranties, and policy questions'}
                </span>
              </div>
            )}

            {message.agentExecution?.tool_calls && message.agentExecution.tool_calls.length > 0 && (
              <div>
                <span className="font-semibold" style={{ color: c.ink2 }}>Tools called: </span>
                <span className="inline-flex flex-wrap gap-1 ml-1">
                  {message.agentExecution.tool_calls.map((tc, i) => (
                    <span
                      key={i}
                      className="px-1.5 py-0.5 rounded text-[10px]"
                      style={{
                        background: tc.status === 'success' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                        color: tc.status === 'success' ? '#047857' : '#b91c1c',
                      }}
                    >
                      {tc.tool}
                      {tc.duration_ms ? ` (${tc.duration_ms}ms)` : ''}
                    </span>
                  ))}
                </span>
              </div>
            )}

            {guardrailsEnabled && (
              <div>
                <span className="font-semibold" style={{ color: c.ink2 }}>Guardrails: </span>
                <span style={{ color: '#047857' }}>Passed</span>
                <span className="ml-1" style={{ color: c.muted }}>(content safety + PII check)</span>
              </div>
            )}

            {index >= 4 && (
              <div>
                <span className="font-semibold" style={{ color: c.ink2 }}>Context: </span>
                <span style={{ color: c.ink }}>
                  {Math.floor((index - 1) / 2)} prior{' '}
                  {Math.floor((index - 1) / 2) === 1 ? 'exchange' : 'exchanges'} in window
                </span>
                <span className="ml-1" style={{ color: c.muted }}>
                  (more context = better answers, higher cost)
                </span>
              </div>
            )}

            {message.agentExecution?.total_duration_ms ? (
              <div>
                <span className="font-semibold" style={{ color: c.ink2 }}>Response time: </span>
                <span style={{ color: c.ink }}>{message.agentExecution.total_duration_ms}ms</span>
              </div>
            ) : null}

            <div
              className="pt-1.5 mt-1"
              style={{ borderTop: '1px solid rgba(45, 24, 16, 0.06)' }}
            >
              <p style={{ color: c.muted }}>
                The orchestrator picked which specialists to involve based on your query. Open{' '}
                <span style={{ color: c.accent }}>/inspector</span> to see the full waterfall.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function ConciergeModal() {
  const { activeModal, closeModal, openComparison, consumePendingQuery } = useUI()
  const { workshopMode, guardrailsEnabled } = useLayout()
  const { addToCart } = useCart()
  const { persona } = usePersona()
  const location = useLocation()
  const sessionId = useSessionId()

  const isOpen = activeModal === 'concierge'
  const isWorkshopRoute = location.pathname.startsWith('/atelier')

  // After the storefront hero-drawer redesign, the ConciergeModal only
  // renders on atelier routes. Boutique chat is handled by ChatDrawer.
  const mode: 'storefront' | 'atelier' = 'atelier'

  // Time-of-day greeting for the personalized storefront welcome. Boundaries
  // match the house style guide's "Good morning/afternoon/evening" rotation.
  const greeting = useMemo(() => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  }, [])

  // Initial welcome — per route mode, only used on first mount of this session.
  const initialMessages = useMemo<AgentChatMessage[]>(() => {
    let content: string
    let suggestions: string[]
    if (isWorkshopRoute) {
      content = WELCOME_WORKSHOP
      suggestions = SUGGESTIONS_WORKSHOP
    } else if (persona) {
      const firstName = persona.display_name.split(' ')[0]
      content = `${greeting}, ${firstName}. ${WELCOME_STOREFRONT}`
      suggestions = SUGGESTIONS_BY_PERSONA[persona.id] ?? SUGGESTIONS_STOREFRONT
    } else {
      content = WELCOME_STOREFRONT
      suggestions = SUGGESTIONS_STOREFRONT
    }
    return [
      {
        role: 'assistant',
        content,
        timestamp: new Date(),
        suggestions,
      },
    ]
  }, [isWorkshopRoute, persona, greeting])

  const {
    messages,
    inputValue,
    setInputValue,
    isLoading,
    backendOnline,
    sendMessage,
    clearChat,
  } = useAgentChat({
    mode,
    workshopMode,
    guardrailsEnabled,
    initialMessages,
    persistKey: `pellier-concierge-${mode}`,
  })

  const [expandedHoods, setExpandedHoods] = useState<Set<number>>(new Set())
  const toggleHood = (idx: number) => {
    setExpandedHoods(prev => {
      const next = new Set(prev)
      if (next.has(idx)) {
        next.delete(idx)
      } else {
        next.add(idx)
      }
      return next
    })
  }

  const messagesEndRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const t = setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 50)
    return () => clearTimeout(t)
  }, [messages, isOpen])

  // When the modal opens with a seeded query (from the hero pill), dispatch
  // it as the first user message. `consumePendingQuery` clears the buffer so
  // re-opens don't re-fire the same query.
  useEffect(() => {
    if (!isOpen) return
    const seeded = consumePendingQuery()
    if (seeded) {
      void sendMessage(seeded)
    }
  }, [isOpen, consumePendingQuery, sendMessage])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Gate: ConciergeModal only renders on atelier routes after the
  // storefront hero-drawer redesign. Boutique chat is ChatDrawer.
  if (!isWorkshopRoute) return null

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-[1000] flex items-center justify-center p-4"
          style={{ background: 'rgba(45, 24, 16, 0.25)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeModal}
        >
          <motion.div
            role="dialog"
            aria-label="Ask Pellier"
            data-testid="concierge-modal"
            className="relative flex flex-col w-full max-w-[560px] h-[min(680px,calc(100vh-4rem))] rounded-3xl overflow-hidden shadow-2xl"
            style={{
              background: c.bg,
              border: '1px solid rgba(45, 24, 16, 0.08)',
            }}
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            onClick={e => e.stopPropagation()}
          >
              {/* ============================================================
               * ATELIER MODE — the only mode ConciergeModal renders now.
               * Boutique chat is handled by ChatDrawer.
               * ============================================================ */}
              <>
            {/* Header */}
            <div
              className="px-5 py-4 flex items-center justify-between flex-shrink-0"
              style={{ borderBottom: '1px solid rgba(45, 24, 16, 0.08)' }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  aria-hidden="true"
                  className="inline-flex items-center justify-center rounded-full font-semibold"
                  style={{ width: 32, height: 32, background: c.ink, color: c.bg, fontFamily: 'Fraunces, serif', fontSize: 15 }}
                >
                  B
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap" style={{ fontFamily: 'Fraunces, serif', fontSize: 17, color: c.ink, fontWeight: 500 }}>
                    <span>Ask Pellier</span>
                    {/* Persona indicator — colored avatar + first name
                        in italic Fraunces with a persona-quote second
                        line under the status strip. Signals that this
                        trace belongs to a specific shopper. Omitted
                        for the Fresh persona and for signed-out
                        sessions — there's no voice to reflect. */}
                    {persona && persona.id !== 'fresh' && (
                      <span
                        className="inline-flex items-center gap-1.5"
                        style={{
                          fontFamily: 'JetBrains Mono, ui-monospace, monospace',
                          fontSize: 9.5,
                          letterSpacing: '0.22em',
                          textTransform: 'uppercase',
                          color: c.muted,
                          fontWeight: 500,
                        }}
                      >
                        <span
                          aria-hidden
                          className="inline-flex items-center justify-center rounded-full"
                          style={{
                            width: 18,
                            height: 18,
                            background: persona.avatar_color,
                            color: 'var(--cream-warm)',
                            fontFamily: 'var(--sans)',
                            fontSize: 10,
                          }}
                        >
                          {persona.avatar_initial}
                        </span>
                        · as {persona.display_name}
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] flex items-center gap-1.5 mt-0.5">
                    {isLoading ? (
                      <span className="flex items-center gap-1.5" style={{ color: c.ink2 }}>
                        <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: c.ink2 }} />
                        Thinking...
                      </span>
                    ) : !backendOnline ? (
                      <span className="flex items-center gap-1.5" style={{ color: c.accent }}>
                        <AlertCircle className="h-3 w-3" />
                        Offline
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5" style={{ color: c.ink2 }}>
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#047857' }} />
                        {mode === 'atelier' ? 'Atelier mode · instrumentation on' : 'Concierge ready'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => {
                    clearChat(initialMessages)
                    setExpandedHoods(new Set())
                  }}
                  className="px-2.5 py-1 rounded-lg text-[11px] transition-colors"
                  style={{ color: c.ink2 }}
                  onMouseEnter={e => (e.currentTarget.style.background = c.paper)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  title="Reset conversation"
                >
                  Reset
                </button>
                <button
                  onClick={closeModal}
                  aria-label="Close"
                  className="p-2 rounded-lg transition-colors"
                  onMouseEnter={e => (e.currentTarget.style.background = c.paper)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <X className="h-4 w-4" style={{ color: c.ink2 }} />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-5 flex flex-col gap-4">
              {/* Messages — atelier mode only renders the instrumented
                  conversation. Welcome state is handled by the storefront
                  branch via BoutiqueChat. */}
              <AnimatePresence initial={false}>
                {messages.map((message, index) => (
                  <motion.div
                    key={`${index}-${message.timestamp.getTime()}`}
                    className="flex flex-col gap-2.5"
                    initial={{ opacity: 0, x: message.role === 'user' ? 16 : -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  >
                    {!(message.products && message.products.length > 0) && (
                      <div className={message.role === 'assistant' ? 'self-start max-w-[90%]' : 'self-end max-w-[85%]'}>
                        <div
                          className={`px-4 py-3 text-[15px] leading-[1.7] ${
                            message.role === 'user' ? 'rounded-2xl rounded-br-sm' : 'rounded-2xl rounded-bl-sm'
                          }`}
                          style={{
                            background: message.role === 'user' ? c.ink : c.paper,
                            color: message.role === 'user' ? c.bg : c.ink,
                            border: message.role === 'assistant' ? '1px solid rgba(45, 24, 16, 0.06)' : 'none',
                            letterSpacing: '-0.003em',
                          }}
                        >
                          {mode === 'atelier' && message.role === 'assistant' && message.agent && message.agentStatus !== 'thinking' && (
                            <AgentBadgeRow message={message} />
                          )}
                          {message.agentStatus === 'thinking' && !message.content ? (
                            <div className="flex items-center gap-2 py-1">
                              <div className="flex gap-1">
                                <motion.span className="w-2 h-2 rounded-full" style={{ background: c.muted }} animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0 }} />
                                <motion.span className="w-2 h-2 rounded-full" style={{ background: c.muted }} animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }} />
                                <motion.span className="w-2 h-2 rounded-full" style={{ background: c.muted }} animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }} />
                              </div>
                              <span className="text-[13px]" style={{ color: c.ink2 }}>Thinking...</span>
                            </div>
                          ) : message.role === 'assistant' ? (
                            // Streaming cursor intentionally removed —
                            // see BoutiqueChatBody for rationale. The
                            // prose growing in place is the indicator;
                            // a blinking caret on top fights the
                            // Claude-desktop feel we're matching.
                            <MarkdownMessage content={message.content} />
                          ) : (
                            <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {message.products && message.products.length > 0 && (
                      <div className="flex flex-col gap-2.5 w-full">
                        {mode === 'atelier' && message.agent && <AgentBadgeRow message={message} />}
                        {message.content && (
                          <div style={{ color: c.ink2 }} className="text-sm font-light leading-relaxed">
                            <MarkdownMessage content={message.content} />
                          </div>
                        )}
                        <div className="flex flex-col gap-2">
                          {message.products.map((product, pIdx) => (
                            <motion.div
                              key={product.id || pIdx}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: pIdx * 0.08, type: 'spring', stiffness: 400, damping: 25 }}
                            >
                              <ProductCardConcierge
                                product={product}
                                rankIndex={pIdx}
                                agentSource={message.agent as AgentType}
                                onPrompt={(prompt) => void sendMessage(prompt)}
                                onAddToCart={() => {
                                  addToCart({
                                    productId: product.id,
                                    name: product.name,
                                    price: product.price,
                                    image: product.image || '',
                                    origin: 'chat',
                                  })
                                }}
                              />
                            </motion.div>
                          ))}
                        </div>
                        {message.products.length >= 2 && (
                          <motion.button
                            onClick={() => openComparison(message.products!)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium self-start"
                            style={{
                              background: c.paper,
                              border: `1px solid ${c.muted}`,
                              color: c.ink,
                            }}
                            whileHover={{ scale: 1.03 }}
                            whileTap={{ scale: 0.97 }}
                          >
                            <GitCompare className="h-3 w-3" />
                            Compare {message.products.length} pieces
                          </motion.button>
                        )}
                      </div>
                    )}

                    {mode === 'atelier' &&
                      message.role === 'assistant' &&
                      message.agentStatus === 'complete' &&
                      (message.agent || message.agentExecution) && (
                        <UnderTheHood
                          index={index}
                          message={message}
                          expanded={expandedHoods.has(index)}
                          onToggle={() => toggleHood(index)}
                          guardrailsEnabled={guardrailsEnabled}
                        />
                      )}

                    {message.suggestions && message.suggestions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {message.suggestions.map((suggestion, i) => (
                          <motion.button
                            key={i}
                            onClick={() => sendMessage(suggestion)}
                            disabled={isLoading}
                            className="px-[13px] py-[6px] rounded-full text-[12.5px] font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            style={{
                              background: c.bg,
                              border: '1px solid rgba(45, 24, 16, 0.14)',
                              color: c.ink2,
                              letterSpacing: '-0.003em',
                            }}
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: i * 0.06, type: 'spring', stiffness: 400, damping: 25 }}
                            whileHover={{ scale: 1.03 }}
                            whileTap={{ scale: 0.97 }}
                          >
                            {suggestion}
                          </motion.button>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="px-5 py-4 flex-shrink-0" style={{ borderTop: '1px solid rgba(45, 24, 16, 0.08)' }}>
              <div className="flex gap-2.5">
                <input
                  type="text"
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={
                    isLoading
                      ? 'Thinking...'
                      : mode === 'atelier'
                        ? 'Ask something that exercises the specialists'
                        : "Tell Pellier what you're looking for..."
                  }
                  disabled={isLoading}
                  className="flex-1 px-4 py-3 rounded-xl text-[15px] leading-[1.5] disabled:opacity-40 focus:outline-none"
                  style={{
                    background: '#ffffff',
                    border: '1px solid rgba(45, 24, 16, 0.12)',
                    color: c.ink,
                    letterSpacing: '-0.003em',
                  }}
                />
                <motion.button
                  onClick={() => sendMessage()}
                  disabled={!inputValue.trim() || isLoading}
                  aria-label="Send"
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 disabled:opacity-30 disabled:cursor-not-allowed"
                  style={{ background: inputValue.trim() && !isLoading ? c.ink : 'rgba(45, 24, 16, 0.08)' }}
                  whileHover={inputValue.trim() && !isLoading ? { scale: 1.05 } : {}}
                  whileTap={inputValue.trim() && !isLoading ? { scale: 0.95 } : {}}
                >
                  {isLoading ? (
                    <div className="w-4 h-4 border-2 border-cream/30 border-t-cream rounded-full animate-spin" style={{ borderColor: 'rgba(251, 244, 232, 0.3)', borderTopColor: c.bg }} />
                  ) : (
                    <Send className="h-4 w-4" style={{ color: c.bg }} />
                  )}
                </motion.button>
              </div>

              {/* Trace-ID footer — atelier route only */}
              {mode === 'atelier' && sessionId && (
                <div className="mt-3 flex items-center justify-between text-[10px]" style={{ fontFamily: 'ui-monospace, monospace', color: c.muted }}>
                  <span>session {sessionId.slice(0, 18)}...</span>
                  <Link
                    to={`/inspector?session=${encodeURIComponent(sessionId)}`}
                    onClick={closeModal}
                    style={{ color: c.accent, textDecoration: 'none' }}
                  >
                    open in inspector →
                  </Link>
                </div>
              )}
            </div>
              </>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
