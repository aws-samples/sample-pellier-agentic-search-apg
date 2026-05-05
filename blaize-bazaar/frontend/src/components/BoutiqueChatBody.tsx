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
import { motion, AnimatePresence } from 'framer-motion'
import type { AgentChatMessage } from '../hooks/useAgentChat'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { CartItemOrigin } from '../contexts/CartContext'
import MarkdownMessage from './MarkdownMessage'
import ProductArtifactCard from './ProductArtifactCard'
import { resolveCover } from './BoutiqueWelcome'
import { useCatalogStats } from '../hooks/useCatalogStats'
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

function toolLabel(
  toolName: string,
  _status: string,
): { label: string; meta?: string } {
  const n = toolName.toLowerCase()
  if (n.includes('find_pieces') || n.includes('search'))
    return { label: 'Searched the boutique' }
  if (n.includes('get_trending') || n.includes('recommendation') || n.includes('get_recommendations'))
    return { label: 'Pulled recommendations' }
  if (n.includes('check_inventory') || n.includes('inventory') || n.includes('get_low_stock'))
    return { label: 'Checked the floor' }
  if (n.includes('get_price') || n.includes('pricing') || n.includes('price_intelligence'))
    return { label: 'Confirmed pricing' }
  if (n.includes('recall') || n.includes('memory') || n.includes('session'))
    return { label: 'Read your last visit' }
  if (n.includes('restock'))
    return { label: 'Flagged for restock' }
  const cleaned = toolName
    .replace(/_/g, ' ')
    .replace(/^get /i, '')
    .replace(/^check /i, 'Checked ')
  return { label: cleaned.charAt(0).toUpperCase() + cleaned.slice(1) }
}

const SKILL_DISPLAY_NAMES: Record<string, string> = {
  'style-advisor': 'Style Advisor',
  'gift-concierge': 'Gift Concierge',
  'the-packing-list': 'Packing List',
  'the-gift-table': 'Gift Table',
  'the-makers-shelf': "Maker's Shelf",
}

function skillDisplayName(canonicalName: string): string {
  return SKILL_DISPLAY_NAMES[canonicalName] ?? canonicalName.replace(/-/g, ' ')
}

function formatAttribution(loadedSkills: string[]): string {
  const names = loadedSkills.map(skillDisplayName)
  if (names.length === 0) return ''
  if (names.length === 1) return `Drawing from the ${names[0]}`
  if (names.length === 2)
    return `Drawing from the ${names[0]} and the ${names[1]}`
  const head = names.slice(0, -1).map((n) => `the ${n}`).join(', ')
  return `Drawing from ${head}, and the ${names[names.length - 1]}`
}

// Follow-up chips align with the canonical 3-turn persona journeys:
//   Turn 1 fires from the hero pill / BoutiqueWelcome pick.
//   Turn 2 + Turn 3 appear as follow-up chips after the first response.
// This keeps the Boutique ↔ Atelier demo narrative coherent.
const FOLLOWUPS_BY_PERSONA: Record<string, string[]> = {
  marco: [
    'What would go with the Pellier shirt?',                // Turn 2
    "What's the price range for linen shirts?",             // Turn 3
    'Is the Pellier shirt at the Brooklyn warehouse?',      // Turn 4 (Stock Keeper payoff)
  ],
  anna: [
    'something beautiful under $100',                    // Turn 2
    'help me pair a candle with something else',          // Turn 3
    'wrap-ready gifts with no extra effort',
  ],
  theo: [
    'what goes well with the pour-over set?',             // Turn 2
    'linen pieces that soften over seasons',              // Turn 3
    'something for the home, not the wardrobe',
  ],
  fresh: [
    'a cozy layer for cooler nights',
    'pieces for slow Sunday mornings',
    'something to wear for warm evenings out',
  ],
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
      <img src={product.imageUrl} alt={product.name} className="ec-persona-cover-img" />
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
}: {
  message: AgentChatMessage
  addToCart: BoutiqueChatBodyProps['addToCart']
  onFollowUp: (text: string) => void
  persona: PersonaSnapshot | null
  isLastAssistantMessage: boolean
}) {
  const isThinking = message.agentStatus === 'thinking' && !message.content
  const isStreaming = message.agentStatus === 'streaming'
  const isComplete = message.agentStatus === 'complete'
  const [thinkingOpen, setThinkingOpen] = useState(!isComplete)

  useEffect(() => {
    if (message.content && message.content.length > 0 && thinkingOpen) {
      setThinkingOpen(false)
    }
  }, [message.content]) // eslint-disable-line react-hooks/exhaustive-deps

  const reasoning = message.agentExecution?.reasoning_steps
  const hasReasoning = reasoning && reasoning.length > 0
  const reasoningText = hasReasoning
    ? reasoning.map((r) => r.content).join(' ')
    : null
  const toolCalls = message.agentExecution?.tool_calls
  const durationSec = message.agentExecution?.total_duration_ms
    ? (message.agentExecution.total_duration_ms / 1000).toFixed(1)
    : null

  return (
    <div className="ec-msg-agent">
      {/* Eyebrow */}
      <div className="ec-msg-agent-eyebrow">
        <span className="ec-b-mini">B</span>
        Blaize
      </div>

      {/* Skill attribution */}
      {message.skillRouting &&
        message.skillRouting.loaded_skills.length > 0 && (
          <div className="ec-msg-attribution">
            {formatAttribution(message.skillRouting.loaded_skills)}
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

      {/* Tool-call lines */}
      {toolCalls && toolCalls.length > 0 && (
        <div className="ec-toolcalls">
          {toolCalls.map((tc, i) => {
            const isActive = tc.status !== 'success' && tc.status !== 'error'
            const { label, meta } = toolLabel(tc.tool, tc.status)
            return (
              <div
                key={i}
                className={`ec-toolcall ${isActive ? 'ec-toolcall-active' : 'ec-toolcall-complete'}`}
              >
                <span className="ec-toolcall-indicator">
                  {isActive ? '\u25CF' : '\u2713'}
                </span>
                <span className="ec-toolcall-label">{label}</span>
                {meta && <span className="ec-toolcall-meta">{meta}</span>}
                {tc.duration_ms > 0 && !meta && (
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
          <MarkdownMessage content={message.content} />
        </div>
      )}

      {/* Product cards — one render path for all products regardless
       * of origin. Past-order references (backend persona-match
       * injection) and forward-looking recs (tool-returned inventory)
       * both surface as full ProductArtifactCards. Keeps the chat's
       * visual register consistent across retrospective and
       * forward-looking turns. */}
      {message.products && message.products.length > 0 && (
        <div className="ec-artifacts">
          {message.products.map((product, pIdx) => (
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
          {followupsForPersona(persona).map((chip) => (
            <button
              key={chip}
              type="button"
              className="ec-followup"
              onClick={() => onFollowUp(chip)}
            >
              {chip}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
