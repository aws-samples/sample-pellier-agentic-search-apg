/**
 * PellierChatBody — message rendering for the storefront chat.
 *
 * Body-only component: renders user bubbles, agent blocks, product
 * cards, and follow-up chips. No header, no footer, no input — those
 * live in the parent surface (ChatDrawer for the storefront).
 *
 * Extracted from PellierChat.tsx so storefront entry points share the same
 * editorial rendering without duplication.
 * All styling comes from storefront-chat.css (the ``ec-*`` classes).
 */
import { useEffect, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { Link } from 'react-router-dom'
import {
  Brain,
  Check,
  ChevronDown,
  CircleAlert,
  Database,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type {
  AgentChatMessage,
  ChatSourceActivity,
} from '../hooks/useAgentChat'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { CartItemOrigin } from '../contexts/CartContext'
import MarkdownMessage from './MarkdownMessage'
import ProductArtifactCard from './ProductArtifactCard'
import StylistHandoffCard from './StylistHandoffCard'
import ChatFailureCard from './ChatFailureCard'
import TurnReceipt from './TurnReceipt'
import GovernedTurnReceipt from './GovernedTurnReceipt'
import { TraceChip } from '../shared/TraceChip'
import { imageSrc } from '../utils/assetPath'
import { catalogTurnFollowUps } from '../utils/catalogFollowUps'
import { awsServiceMark } from '../utils/awsServiceMarks'
import { nextJourneyPrompt } from '../data/workshopJourneys'
import { CHAT_TRUST, SCENARIO } from '../copy'
import '../styles/pellier-chat.css'
import '../styles/pellier-welcome.css'
import PellierMark from './PellierMark'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PellierChatBodyProps {
  messages: AgentChatMessage[]
  sendMessage: (text?: string) => Promise<void>
  retryMessage: (text: string) => Promise<void>
  onEditRequest: (text: string) => void
  onAuthenticate: () => void
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
// Helpers (shared with PellierChat — kept here as the canonical copy)
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
  'the-packing-list': 'skill.packing-list',
  'the-gift-table': 'skill.gift-table',
  'the-makers-shelf': 'skill.makers-shelf',
  'the-care-card': 'skill.care-card',
  'the-proof-counter': 'skill.proof-counter',
}

function skillTraceTool(canonical: string): string {
  return SKILL_TRACE[canonical] ?? `skill.${canonical.replace(/^the-/, '')}`
}

function toolTraceTool(toolName: string): string {
  return toolName.includes('.') ? toolName : `tool.${toolName}`
}

function sourceIdentity(source: string): {
  Icon: LucideIcon
  tone: 'database' | 'memory' | 'model' | 'control' | 'neutral'
} {
  const value = source.toLowerCase()
  if (value.includes('postgres') || value.includes('aurora')) {
    return { Icon: Database, tone: 'database' }
  }
  if (value.includes('memory')) return { Icon: Brain, tone: 'memory' }
  if (value.includes('bedrock')) return { Icon: Sparkles, tone: 'model' }
  if (value.includes('control') || value.includes('policy')) {
    return { Icon: ShieldCheck, tone: 'control' }
  }
  return { Icon: Database, tone: 'neutral' }
}

function SourceActivityRow({ activity }: { activity: ChatSourceActivity }) {
  const { Icon, tone } = sourceIdentity(activity.source)
  const mark = awsServiceMark(activity.source)
  const working = activity.status === 'in_progress'
  const unavailable = activity.status === 'unavailable'
  const details = Array.isArray(activity.details) ? activity.details : []
  return (
    <div className="ec-source-row" data-source-tone={tone} data-status={activity.status}>
      {/* An AWS service mark is a filled square badge in its own category
          colour, so it replaces the tinted circle rather than sitting inside
          it. Same 22px footprint either way, so the row rhythm is unchanged. */}
      <span
        className="ec-source-icon"
        data-mark={mark ? 'aws' : undefined}
        aria-hidden="true"
      >
        {mark ? (
          <img src={imageSrc(mark.src)} alt="" width={22} height={22} />
        ) : (
          <Icon size={14} strokeWidth={1.8} />
        )}
      </span>
      <span className="ec-source-copy">
        <span className="ec-source-name">{activity.source}</span>
        {details.map((detail) => (
          <span className="ec-source-detail" key={detail}>{detail}</span>
        ))}
      </span>
      <span className="ec-source-status">
        {working && <LoaderCircle size={11} strokeWidth={2} aria-hidden="true" />}
        {working ? 'Working' : unavailable ? 'Unavailable' : 'Used'}
      </span>
    </div>
  )
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
  return mentioned
    .sort((a, b) => {
      if (a.mentionIndex !== b.mentionIndex) {
        return a.mentionIndex - b.mentionIndex
      }
      return a.index - b.index
    })
    .map((item) => item.product)
    .slice(0, 3)
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

/**
 * Follow-up chips for one answered turn.
 *
 * The scripted next turn leads when there is one. A participant who clicked
 * Marco's "What linen do you have for 10 days in Goa?" is offered "What would
 * go with the Hadley shirt?" rather than a generic catalog action, so the
 * three-turn journey flows without anyone retyping it — and the room stays on
 * its clock. Catalog actions fill the remaining slots, so the chips still
 * respond to what the answer actually returned.
 *
 * Capped at three. These chips are a bounded nudge, not a menu.
 */
const MAX_FOLLOWUPS = 3

function followupsForMessage(
  message: AgentChatMessage,
  precedingUserQuery: string | undefined,
): string[] {
  const catalog = catalogTurnFollowUps(
    (message.products ?? []).filter((product) => product.ownership !== 'owned'),
    [],
  )
  const scripted = nextJourneyPrompt(precedingUserQuery)
  if (!scripted) return catalog.slice(0, MAX_FOLLOWUPS)
  return [scripted, ...catalog.filter((chip) => chip !== scripted)].slice(
    0,
    MAX_FOLLOWUPS,
  )
}

// ---------------------------------------------------------------------------
// Persona cover banner
//
// The profile image is a durable Aurora value carried by PersonaContext.
// ---------------------------------------------------------------------------
function PersonaCoverBanner({ persona }: { persona: PersonaSnapshot | null }) {
  if (!persona) return null

  return (
    <div className="ec-persona-cover">
      <img
        src={imageSrc(persona.hero_image)}
        alt={persona.hero_alt}
        className="ec-persona-cover-img"
      />
      <div className="ec-persona-cover-overlay">
        <div className="ec-persona-cover-eyebrow">
          <span className="ec-persona-cover-dot" />
          {SCENARIO.active(persona.display_name)}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Body component
// ---------------------------------------------------------------------------

export default function PellierChatBody({
  messages,
  sendMessage,
  retryMessage,
  onEditRequest,
  onAuthenticate,
  addToCart,
  persona,
}: PellierChatBodyProps) {
  const reducedMotion = useReducedMotion()
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
            initial={reducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.25, ease: 'easeOut' }}
          >
            {message.role === 'user' ? (
              <UserMessage message={message} />
            ) : (
              <AgentMessage
                message={message}
                addToCart={addToCart}
                isLastAssistantMessage={index === lastAssistantIndex}
                precedingUserQuery={
                  messages
                    .slice(0, index)
                    .reverse()
                    .find((earlier) => earlier.role === 'user')?.content
                }
                onFollowUp={(text) => void sendMessage(text)}
                onRetry={(text) => void retryMessage(text)}
                onEditRequest={onEditRequest}
                onAuthenticate={onAuthenticate}
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
        <span
          aria-hidden="true"
          style={{
            width: 4,
            height: 4,
            borderRadius: 999,
            background: 'var(--red-1)',
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
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
  onRetry,
  onEditRequest,
  onAuthenticate,
  isLastAssistantMessage,
  precedingUserQuery,
}: {
  message: AgentChatMessage
  addToCart: PellierChatBodyProps['addToCart']
  onFollowUp: (text: string) => void
  onRetry: (text: string) => void
  onEditRequest: (text: string) => void
  onAuthenticate: () => void
  isLastAssistantMessage: boolean
  /** The question this answer replies to, used to find the next scripted turn. */
  precedingUserQuery: string | undefined
}) {
  const reducedMotion = useReducedMotion()
  const isThinking = message.agentStatus === 'thinking' && !message.content
  const isStreaming = message.agentStatus === 'streaming'
  const isComplete = message.agentStatus === 'complete'
  const [thinkingOpen, setThinkingOpen] = useState(!isComplete)
  const [attributionOpen, setAttributionOpen] = useState(!isComplete)

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
  const sourceActivity = message.sourceActivity ?? []
  const traceReference = message.agentExecution?.trace_id ?? undefined
  // The trace id is the preferred reference; a turn that emitted none still
  // has a turn id worth copying into the Observatory.
  const receiptReference = traceReference ?? message.turnId
  // A failed turn has no match to detail: the failure card is the whole story.
  const hasAttribution =
    !message.failure &&
    (sourceActivity.length > 0 ||
      loadedSkills.length > 0 ||
      dedupedToolCalls.length > 0 ||
      !!receiptReference)
  const attributionSummary = [
    sourceActivity.length > 0
      ? `${sourceActivity.length} ${sourceActivity.length === 1 ? 'source' : 'sources'}`
      : null,
    loadedSkills.length > 0
      ? `${loadedSkills.length} specialty edit${loadedSkills.length === 1 ? '' : 's'}`
      : null,
    dedupedToolCalls.length
      ? `${dedupedToolCalls.length} check${dedupedToolCalls.length === 1 ? '' : 's'}`
      : null,
    receiptReference ? 'turn reference' : null,
  ].filter(Boolean).join(' · ')

  useEffect(() => {
    if (isComplete) {
      setAttributionOpen(false)
    } else if (hasAttribution) {
      setAttributionOpen(true)
    }
  }, [hasAttribution, isComplete])

  const durationSec = message.agentExecution?.total_duration_ms
    ? (message.agentExecution.total_duration_ms / 1000).toFixed(1)
    : null
  const orderedProducts = message.products
    ? productsForRenderedProse(message.products, message.content)
    : []
  const recommendedProducts = orderedProducts.filter(
    (product) => product.ownership !== 'owned',
  )
  const ownedProducts = orderedProducts.filter(
    (product) => product.ownership === 'owned',
  )
  const displayContent =
    orderedProducts.length > 0
      ? emphasizeProductMentionsAndPrices(message.content, orderedProducts)
      : message.content
  return (
    <div
      className="ec-msg-agent"
      aria-live={isStreaming ? 'polite' : undefined}
      aria-atomic={isStreaming ? 'false' : undefined}
    >
      {/* Eyebrow */}
      <div className="ec-msg-agent-eyebrow">
        <PellierMark size={18} />
        Pellier
      </div>

      {/* Skills + tool calls — collapsed by default so Pellier stays calm,
          with a Claude-style disclosure for curious shoppers. */}
      {hasAttribution && (
        <div
          className={[
            'ec-worked',
            attributionOpen ? 'ec-worked-open' : '',
            !isComplete ? 'ec-worked-live' : '',
          ].filter(Boolean).join(' ')}
          data-testid="storefront-source-disclosure"
        >
          <button
            type="button"
            className="ec-worked-header"
            aria-expanded={attributionOpen}
            onClick={() => setAttributionOpen((open) => !open)}
          >
            <span className="ec-worked-status" aria-hidden="true">
              {!isComplete ? (
                <LoaderCircle size={14} strokeWidth={1.9} />
              ) : (
                <Check size={14} strokeWidth={1.9} />
              )}
            </span>
            <span className="ec-worked-title">
              {!isComplete ? 'Working with live sources' : CHAT_TRUST.MATCH_DETAILS}
            </span>
            <span className="ec-worked-summary">{attributionSummary}</span>
            <ChevronDown
              className={`ec-worked-chevron ${attributionOpen ? 'ec-worked-chevron-open' : ''}`}
              size={14}
              strokeWidth={1.8}
              aria-hidden="true"
            />
          </button>

          {attributionOpen && (
            <div className="ec-worked-body">
              {sourceActivity.length > 0 && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">Sources used</div>
                  <div className="ec-source-list">
                    {sourceActivity.map((activity) => (
                      <SourceActivityRow
                        key={activity.source}
                        activity={activity}
                      />
                    ))}
                  </div>
                </div>
              )}

              {loadedSkills.length > 0 && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">Specialty edit</div>
                  <div className="ec-msg-attribution">
                    {loadedSkills.map((skill) => (
                      <TraceChip key={skill} tool={skillTraceTool(skill)} compact labelMode="label" />
                    ))}
                  </div>
                </div>
              )}

              {dedupedToolCalls.length > 0 && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">Catalog checks</div>
                  <div className="ec-toolcalls">
                    {dedupedToolCalls.map((tc, i) => {
                      const isActive = [
                        'executing',
                        'in_progress',
                        'pending',
                        'running',
                      ].includes(tc.status)
                      const failed = tc.status === 'error' || tc.status === 'failed'
                      return (
                        <div
                          key={`${tc.tool}-${i}`}
                          className={[
                            'ec-toolcall',
                            isActive
                              ? 'ec-toolcall-active'
                              : failed
                                ? 'ec-toolcall-failed'
                                : 'ec-toolcall-complete',
                          ].join(' ')}
                        >
                          <span className="ec-toolcall-indicator">
                            {isActive ? (
                              <LoaderCircle size={13} strokeWidth={1.9} aria-hidden="true" />
                            ) : failed ? (
                              <CircleAlert size={13} strokeWidth={1.9} aria-hidden="true" />
                            ) : (
                              <Check size={13} strokeWidth={1.9} aria-hidden="true" />
                            )}
                          </span>
                          <TraceChip tool={toolTraceTool(tc.tool)} compact labelMode="label" />
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

              {receiptReference && (
                <div className="ec-worked-section">
                  <div className="ec-worked-section-label">
                    {CHAT_TRUST.TURN_RECEIPT}
                  </div>
                  <TurnReceipt
                    reference={receiptReference}
                    turnId={message.turnId}
                    complete={isComplete}
                  />
                </div>
              )}

            </div>
          )}
        </div>
      )}

      {/* Compact governed receipt — deliberately outside the collapsed
          "how this worked" disclosure. Its fields come only from the
          authenticated, persisted turn record; a card count or a local
          instrumentation array is not citation or execution evidence. */}
      {isComplete && !message.failure && (
        <GovernedTurnReceipt
          sessionId={message.sessionId}
          turnId={message.turnId}
          railDecision={message.railDecision}
        />
      )}

      {message.failure && (
        <ChatFailureCard
          failure={message.failure}
          onRetry={onRetry}
          onEditRequest={onEditRequest}
          onAuthenticate={onAuthenticate}
        />
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
          PellierChat.tsx so the rendering path is byte-identical. */}
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

      {/* Message body grows phrase by phrase with a restrained editorial caret. */}
      {message.content && (
        <div className={`ec-msg-body ${isStreaming ? 'ec-msg-streaming' : ''}`}>
          <MarkdownMessage content={displayContent} streaming={isStreaming} />
        </div>
      )}

      {/* Stylist handoff card — escalation tool fired. Replaces the
       * product grid for this turn; product buffering was already
       * suppressed server-side so orderedProducts is empty. */}
      {message.escalation && <StylistHandoffCard handoff={message.escalation} />}

      {/* Prepared, not carried out. The governed boundary declined the mutation and a
       * person has to confirm it.
       *
       * This is deliberately NOT part of the answer prose. The specialist prompt asks
       * for the sentence and the model dropped it, leaving the shopper told only that
       * their request was "prepared" — which reads as filed. The backend supplies the
       * wording and this renders it, so no paraphrase can lose the guarantee.
       *
       * Product lookups used to resolve the order are action plumbing, not a
       * recommendation shelf, so pending-review turns do not merchandise them. */}
      {message.reviewPending && (
        <div
          className="ec-review-pending"
          data-testid="pellier-review-pending"
          role="status"
        >
          <p>{message.reviewPending.message}</p>
          {message.reviewPending.reviewId ? (
            <Link to={`/operator/reviews/${message.reviewPending.reviewId}`}>
              Open prepared request in Operator
            </Link>
          ) : null}
        </div>
      )}

      {recommendedProducts.length > 0 && !message.reviewPending && (
        <div className="ec-artifacts">
          {recommendedProducts.map((product, pIdx) => (
            <motion.div
              key={product.id || pIdx}
              initial={reducedMotion ? false : { opacity: 0, y: 8, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={reducedMotion
                ? { duration: 0 }
                : {
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

      {ownedProducts.length > 0 && !message.reviewPending && (
        <section className="ec-owned-artifacts" aria-labelledby="collection-pieces-heading">
          <div id="collection-pieces-heading" className="ec-owned-artifacts-label">
            Already in your collection
          </div>
          <div className="ec-artifacts">
            {ownedProducts.map((product, pIdx) => (
              <motion.div
                key={product.id || pIdx}
                initial={reducedMotion ? false : { opacity: 0, y: 8, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={reducedMotion
                  ? { duration: 0 }
                  : {
                      delay: pIdx * 0.1,
                      duration: 0.38,
                      ease: [0.2, 0.9, 0.3, 1.05],
                    }}
              >
                <ProductArtifactCard
                  product={product}
                  rankIndex={pIdx}
                  onPrompt={(prompt) => onFollowUp(prompt)}
                />
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Follow-up chips */}
      {isComplete && isLastAssistantMessage && !message.failure && (
        <div className="ec-followups">
          {followupsForMessage(message, precedingUserQuery).map((chip) => (
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
