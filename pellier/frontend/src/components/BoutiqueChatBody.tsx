/**
 * BoutiqueChatBody — message rendering for the storefront chat.
 *
 * Body-only component: renders user bubbles, agent blocks, product
 * cards, and follow-up chips. No header, no footer, no input — those
 * live in the parent surface (ChatDrawer for storefront, ConciergeModal
 * for atelier).
 *
 * Extracted from BoutiqueChat.tsx so both the drawer and the legacy
 * modal can consume the same editorial rendering without duplication.
 * All styling comes from storefront-chat.css (the ``ec-*`` classes).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import type { AgentChatMessage } from '../hooks/useAgentChat'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { CartItemOrigin } from '../contexts/CartContext'
import MarkdownMessage from './MarkdownMessage'
import ProductArtifactCard from './ProductArtifactCard'
import StylistHandoffCard from './StylistHandoffCard'
import { TraceChip } from '../shared/TraceChip'
import { resolveCover } from './BoutiqueWelcome'
import { PERSONA_HERO_PILLS, MARCO_BUILDER_SESSION_QUERY } from '../data/personaCurations'
import { useFloorCheckWorkshopCue } from '../hooks/useFloorCheckWorkshopCue'
import { useCatalogStats } from '../hooks/useCatalogStats'
import { imageSrc } from '../utils/assetPath'
import '../styles/boutique-chat.css'
import '../styles/boutique-welcome.css'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BoutiqueChatBodyProps {
  messages: AgentChatMessage[]
  sendMessage: (text?: string) => Promise<void>
  addToCart: (item: {
    productId: number
    name: string
    price: number
    image?: string
    origin: CartItemOrigin
  }) => void
  persona: PersonaSnapshot | null
}

// ---------------------------------------------------------------------------
// Helpers (shared with BoutiqueChat — kept here as the canonical copy)
// ---------------------------------------------------------------------------

function relativeTime(ts: Date): string {
  const diff = Date.now() - ts.getTime()
  if (diff < 60_000) return 'just now'
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ago`
}

/** Dot-notation trace labels for loaded skills (same register as memory.recall). */
const SKILL_TRACE: Record<string, string> = {
  'style-advisor': 'skill.style-advisor',
  'gift-concierge': 'skill.gift-concierge',
  'the-packing-list': 'skill.packing-list',
  'the-gift-table': 'skill.gift-table',
  'the-makers-shelf': 'skill.makers-shelf',
}

function skillTraceTool(canonical: string): string {
  return SKILL_TRACE[canonical] ?? `skill.${canonical.replace(/^the-/, '')}`
}

function toolTraceTool(toolName: string): string {
  return toolName.includes('.') ? toolName : `tool.${toolName}`
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function productsForRenderedProse(
  products: NonNullable<AgentChatMessage['products']>,
  content: string,
): NonNullable<AgentChatMessage['products']> {
  const normalizedContent = content.toLowerCase()
  const ranked = products.map((product, index) => ({
    product,
    index,
    mentionIndex: product.name
      ? normalizedContent.indexOf(product.name.toLowerCase())
      : -1,
  }))
  const mentioned = ranked.filter((item) => item.mentionIndex >= 0)
  if (mentioned.length === 0) return products
  const orderedMentioned = mentioned
    .sort((a, b) => {
      if (a.mentionIndex !== b.mentionIndex) {
        return a.mentionIndex - b.mentionIndex
      }
      return a.index - b.index
    })
    .map((item) => item.product)

  // Keep prose alignment as the primary rule, but ensure discovery turns
  // still show a usable shelf when the model only names one or two picks.
  // Backfill from original ranked tool results to a floor of 3 cards.
  if (orderedMentioned.length >= 3) return orderedMentioned

  const seen = new Set(
    orderedMentioned.map((product) => `${product.id ?? ''}::${product.name ?? ''}`),
  )
  const backfill = products.filter((product) => {
    const key = `${product.id ?? ''}::${product.name ?? ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  return [...orderedMentioned, ...backfill].slice(0, Math.min(3, products.length))
}

function emphasizeProductMentionsAndPrices(
  content: string,
  products: NonNullable<AgentChatMessage['products']>,
): string {
  const names = Array.from(
    new Set(
      products
        .map((product) => product.name?.trim())
        .filter((name): name is string => !!name),
    ),
  ).sort((a, b) => b.length - a.length)

  if (names.length === 0) return content

  // Leave existing markdown bold spans and code fences untouched.
  return content
    .split(/(```[\s\S]*?```|\*\*.*?\*\*)/g)
    .map((segment) => {
      if (segment.startsWith('```') || segment.startsWith('**')) return segment
      return names.reduce((text, name) => {
        const pattern = new RegExp(`(${escapeRegExp(name)})`, 'gi')
        return text.replace(pattern, '**$1**')
      }, segment).replace(/(\$\d+(?:,\d{3})*(?:\.\d{2})?)/g, '**$1**')
    })
    .join('')
}

// Follow-up chips = Turns 2–5 for each persona: same strings as the
// Boutique hero row (PERSONA_HERO_PILLS), omitting Turn 1 (already sent
// from the hero pill / welcome pick).
const FOLLOWUPS_BY_PERSONA: Record<string, string[]> = {
  marco: PERSONA_HERO_PILLS.marco.slice(1),
  anna: PERSONA_HERO_PILLS.anna.slice(1),
  theo: PERSONA_HERO_PILLS.theo.slice(1),
  fresh: PERSONA_HERO_PILLS.fresh.slice(1),
}

function followupsForPersona(persona?: PersonaSnapshot | null): string[] {
  if (!persona) return FOLLOWUPS_BY_PERSONA.fresh
  return FOLLOWUPS_BY_PERSONA[persona.id] ?? FOLLOWUPS_BY_PERSONA.fresh
}

// Time-of-day helper for cover eyebrow resolution. Duplicated from
// BoutiqueWelcome so the chat body stays self-contained.
type TimeOfDay = 'morning' | 'afternoon' | 'evening'
function timeOfDay(): TimeOfDay {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}

// ---------------------------------------------------------------------------
// Persona cover banner
//
// Compact editorial banner that sits above the chat stream. Shows the
// same persona-matched cover image the BoutiqueWelcome hero used, so
// the warm "standout" moment doesn't vanish the second the user fires
// their first query. Resolves per persona via resolveCover().
// ---------------------------------------------------------------------------
function PersonaCoverBanner({ persona }: { persona: PersonaSnapshot | null }) {
  const stats = useCatalogStats()
  const tod = timeOfDay()
  const { product, eyebrow } = resolveCover(persona, stats, tod)

  return (
    <div className="ec-persona-cover">
      <img src={imageSrc(product.imageUrl)} alt={product.name} className="ec-persona-cover-img" />
      <div className="ec-persona-cover-overlay">
        <div className="ec-persona-cover-eyebrow">
          <span className="ec-persona-cover-dot" />
          {eyebrow}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Body component
// ---------------------------------------------------------------------------

export default function BoutiqueChatBody({
  messages,
  sendMessage,
  addToCart,
  persona,
}: BoutiqueChatBodyProps) {
  const { showBuilderSessionGap } = useFloorCheckWorkshopCue()
  const lastAssistantIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return i
    }
    return -1
  })()

  return (
    <>
      <PersonaCoverBanner persona={persona} />
    <AnimatePresence initial={false}>
      {messages.map((message, index) => {
        return (
          <motion.div
            key={`msg-${index}-${message.timestamp.getTime()}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            {message.role === 'user' ? (
              <UserMessage message={message} />
            ) : (
              <AgentMessage
                message={message}
                addToCart={addToCart}
                persona={persona}
                isLastAssistantMessage={index === lastAssistantIndex}
                onFollowUp={(text) => void sendMessage(text)}
                showBuilderSessionGap={showBuilderSessionGap}
              />
            )}
          </motion.div>
        )
      })}
    </AnimatePresence>
    </>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function UserMessage({ message }: { message: AgentChatMessage }) {
  return (
    <div className="ec-msg-user">
      <div className="ec-msg-user-eyebrow">
        <span style={{ color: 'var(--red-1)' }}>&middot;</span>
        You &middot; {relativeTime(message.timestamp)}
      </div>
      <div className="ec-msg-user-text">{message.content}</div>
    </div>
  )
}

function AgentMessage({
  message,
  addToCart,
  onFollowUp,
  persona,
  isLastAssistantMessage,
  showBuilderSessionGap,
}: {
  message: AgentChatMessage
  addToCart: BoutiqueChatBodyProps['addToCart']
  onFollowUp: (text: string) => void
  persona: PersonaSnapshot | null
  isLastAssistantMessage: boolean
  showBuilderSessionGap: boolean
}) {
  const isThinking = message.agentStatus === 'thinking' && !message.content
  const isStreaming = message.agentStatus === 'streaming'
  const isComplete = message.agentStatus === 'complete'
  const [thinkingOpen, setThinkingOpen] = useState(!isComplete)
  const [attributionOpen, setAttributionOpen] = useState(false)

  useEffect(() => {
    if (message.content && message.content.length > 0 && thinkingOpen) {
      setThinkingOpen(false)
    }
  }, [message.content])

  const reasoning = message.agentExecution?.reasoning_steps
  const hasReasoning = reasoning && reasoning.length > 0
  const reasoningText = hasReasoning
    ? reasoning.map((r) => r.content).join(' ')
    : null
  const toolCalls = message.agentExecution?.tool_calls ?? []
  const dedupedToolCalls = Array.from(
    toolCalls
      .reduce(
        (byTool, toolCall) => byTool.set(toolCall.tool, toolCall),
        new Map<string, (typeof toolCalls)[number]>(),
      )
      .values(),
  )
  const loadedSkills = message.skillRouting?.loaded_skills ?? []
  const showAnnaRetrievalLink =
    persona?.id === 'anna' &&
    dedupedToolCalls.some((toolCall) =>
      toolCall.tool.toLowerCase().includes('find_pieces_hybrid'),
    )
  const hasAttribution = loadedSkills.length > 0 || dedupedToolCalls.length > 0
  const attributionSummary = [
    loadedSkills.length > 0
      ? `${loadedSkills.length} skill${loadedSkills.length === 1 ? '' : 's'}`
      : null,
    dedupedToolCalls.length
      ? `${dedupedToolCalls.length} tool${dedupedToolCalls.length === 1 ? '' : 's'}`
      : null,
  ].filter(Boolean).join(' · ')
  const durationSec = message.agentExecution?.total_duration_ms
    ? (message.agentExecution.total_duration_ms / 1000).toFixed(1)
    : null
  const orderedProducts = message.products
    ? productsForRenderedProse(message.products, message.content)
    : []
  const displayContent =
    orderedProducts.length > 0
      ? emphasizeProductMentionsAndPrices(message.content, orderedProducts)
      : message.content

  return (
    <div className="ec-msg-agent">
      {/* Eyebrow */}
      <div className="ec-msg-agent-eyebrow">
        <span className="ec-b-mini">P</span>
        Pellier
      </div>

      {/* Skills + tool calls — collapsed by default so Boutique stays calm,
          with a Claude-style disclosure for curious shoppers. */}
      {hasAttribution && (
        <div className={`ec-worked ${attributionOpen ? 'ec-worked-open' : ''}`}>
          <button
            type="button"
            className="ec-worked-header"
            aria-expanded={attributionOpen}
            onClick={() => setAttributionOpen((open) => !open)}
          >
            <span className="ec-worked-dot" aria-hidden="true" />
            <span className="ec-worked-title">Under the hood</span>
            <span className="ec-worked-summary">{attributionSummary}</span>
            <span className={`ec-worked-chevron ${attributionOpen ? 'ec-worked-chevron-open' : ''}`}>
              &#x25BE;
            </span>
          </button>

          {attributionOpen && (
            <div className="ec-worked-body">
              {loadedSkills.length > 0 && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">Skills</div>
                  <div className="ec-msg-attribution">
                    {loadedSkills.map((skill) => (
                      <TraceChip key={skill} tool={skillTraceTool(skill)} compact />
                    ))}
                  </div>
                </div>
              )}

              {dedupedToolCalls.length > 0 && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">Tools</div>
                  <div className="ec-toolcalls">
                    {dedupedToolCalls.map((tc, i) => {
                      const isActive = tc.status !== 'success' && tc.status !== 'error'
                      return (
                        <div
                          key={`${tc.tool}-${i}`}
                          className={`ec-toolcall ${isActive ? 'ec-toolcall-active' : 'ec-toolcall-complete'}`}
                        >
                          <span className="ec-toolcall-indicator">
                            {isActive ? '\u25CF' : '\u2713'}
                          </span>
                          <TraceChip tool={toolTraceTool(tc.tool)} compact />
                          {tc.duration_ms > 0 && (
                            <span className="ec-toolcall-meta">
                              {tc.duration_ms < 1000
                                ? `${tc.duration_ms}ms`
                                : `${(tc.duration_ms / 1000).toFixed(1)}s`}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {showAnnaRetrievalLink && (
                <Link className="ec-worked-link" to="/atelier/performance">
                  Compare retrieval strategies in Atelier
                  <span aria-hidden="true">↗</span>
                </Link>
              )}
            </div>
          )}
        </div>
      )}

      {/* Thinking state — inline dots when no reasoning yet */}
      {isThinking && !hasReasoning && (
        <div className="ec-thinking-inline">
          <span className="ec-thinking-label">Considering</span>
          <span className="ec-dot-typing ec-dot-typing-sm" />
        </div>
      )}

      {/* Thinking block — collapsible with shimmer. In storefront mode
          agentExecution is typically undefined so hasReasoning is false
          and this block never renders. Kept for structural parity with
          BoutiqueChat.tsx so the rendering path is byte-identical. */}
      {hasReasoning && (
        <div className={`ec-thinking ${thinkingOpen ? 'ec-thinking-open' : ''}`}>
          <button
            type="button"
            className="ec-thinking-header"
            onClick={() => setThinkingOpen((o) => !o)}
          >
            <div className="ec-thinking-header-left">
              <span className="ec-thinking-header-label">Considering</span>
              {durationSec && (
                <span className="ec-thinking-header-duration">{durationSec}s</span>
              )}
            </div>
            <span className={`ec-thinking-chevron ${thinkingOpen ? 'ec-thinking-chevron-open' : ''}`}>
              &#x25BE;
            </span>
          </button>
          {thinkingOpen && (
            <div className="ec-thinking-body">
              <p className={isStreaming && !message.content ? 'shimmer-text' : ''}>
                {reasoningText}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Message body.
       *
       * Streaming cursor intentionally omitted — the prose itself grows
       * in place which is enough of a tell. Adding a caret on top
       * produced a distracting blink that didn't match the Claude
       * desktop feel. The `ec-msg-streaming` class still applies its
       * subtle breathing animation.
       */}
      {message.content && (
        <div className={`ec-msg-body ${isStreaming ? 'ec-msg-streaming' : ''}`}>
          <MarkdownMessage content={displayContent} />
        </div>
      )}

      {/* Stylist handoff card — escalation tool fired. Replaces the
       * product grid for this turn; product buffering was already
       * suppressed server-side so orderedProducts is empty. */}
      {message.escalation && <StylistHandoffCard handoff={message.escalation} />}

      {/* Product cards — one render path for all products regardless
       * of origin. Past-order references (backend persona-match
       * injection) and forward-looking recs (tool-returned inventory)
       * both surface as full ProductArtifactCards. Keeps the chat's
       * visual register consistent across retrospective and
       * forward-looking turns. */}
      {orderedProducts.length > 0 && (
        <div className="ec-artifacts">
          {orderedProducts.map((product, pIdx) => (
            <motion.div
              key={product.id || pIdx}
              initial={{ opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{
                delay: pIdx * 0.1,
                duration: 0.38,
                ease: [0.2, 0.9, 0.3, 1.05],
              }}
            >
              <ProductArtifactCard
                product={product}
                rankIndex={pIdx}
                onPrompt={(prompt) => onFollowUp(prompt)}
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
      )}

      {/* Follow-up chips */}
      {isComplete && isLastAssistantMessage && (
        <div className="ec-followups">
          {followupsForPersona(persona).map((chip) => {
            const workshopMarcoChip =
              persona?.id === 'marco' &&
              showBuilderSessionGap &&
              chip === MARCO_BUILDER_SESSION_QUERY
            return (
              <button
                key={chip}
                type="button"
                className={
                  workshopMarcoChip
                    ? 'ec-followup ec-followup-workshop'
                    : 'ec-followup'
                }
                title={
                  workshopMarcoChip
                    ? 'Your exercise: wire floor_check so Stock Keeper can answer this turn from live inventory.'
                    : undefined
                }
                onClick={() => onFollowUp(chip)}
              >
                {chip}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
