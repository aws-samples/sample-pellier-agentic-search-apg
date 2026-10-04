/**
 * PellierChatBody: message rendering for the storefront chat.
 *
 * Body-only component: renders user bubbles and agent turns. No header, no
 * footer, no input; those live in ChatDrawer. An agent turn is the "show the
 * work" layout: one status line with the pulsing copper dot, the compact
 * step list with its findings, the answer settling in character by
 * character, then the product cards after the sentence that names them.
 * With the Builder view on, each step adds its layer tags and evidence.
 */
import { useCallback, useMemo, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { Link } from 'react-router-dom'
import type { AgentChatMessage } from '../hooks/useAgentChat'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { CartItemOrigin } from '../contexts/CartContext'
import ProductArtifactCard from './ProductArtifactCard'
import StylistHandoffCard from './StylistHandoffCard'
import ChatFailureCard from './ChatFailureCard'
import { RevealedProse, StatusLine, StepList, sentenceEndAfter } from './turn'
import { imageSrc } from '../utils/assetPath'
import { catalogTurnFollowUps } from '../utils/catalogFollowUps'
import { nextJourneyPrompt } from '../data/workshopJourneys'
import { SCENARIO } from '../copy'
import '../styles/pellier-chat.css'
import '../styles/pellier-welcome.css'
import '../styles/turn.css'
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
  /** Show layer tags, evidence lines and the ranking panel on each step. */
  builderView?: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(ts: Date): string {
  const diff = Date.now() - ts.getTime()
  if (diff < 60_000) return 'just now'
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ago`
}

type Products = NonNullable<AgentChatMessage['products']>

/** The products the prose names, in order of first mention, at most three. */
function productsForRenderedProse(products: Products, content: string): Products {
  const normalizedContent = content.toLowerCase()
  return products
    .map((product, index) => ({
      product,
      index,
      mentionIndex: product.name ? normalizedContent.indexOf(product.name.toLowerCase()) : -1,
    }))
    .filter((item) => item.mentionIndex >= 0)
    .sort((a, b) => (a.mentionIndex !== b.mentionIndex ? a.mentionIndex - b.mentionIndex : a.index - b.index))
    .map((item) => item.product)
    .slice(0, 3)
}

/**
 * Follow-up chips for one answered turn. The scripted next turn leads when
 * there is one; catalog actions fill the remaining slots. Capped at three.
 */
const MAX_FOLLOWUPS = 3

function followupsForMessage(message: AgentChatMessage, precedingUserQuery: string | undefined): string[] {
  const catalog = catalogTurnFollowUps(
    (message.products ?? []).filter((product) => product.ownership !== 'owned'),
    [],
  )
  const scripted = nextJourneyPrompt(precedingUserQuery)
  if (!scripted) return catalog.slice(0, MAX_FOLLOWUPS)
  return [scripted, ...catalog.filter((chip) => chip !== scripted)].slice(0, MAX_FOLLOWUPS)
}

// ---------------------------------------------------------------------------
// Persona cover banner
// ---------------------------------------------------------------------------
function PersonaCoverBanner({ persona }: { persona: PersonaSnapshot | null }) {
  if (!persona) return null
  return (
    <div className="ec-persona-cover">
      <img src={imageSrc(persona.hero_image)} alt={persona.hero_alt} className="ec-persona-cover-img" />
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
  builderView = false,
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
        {messages.map((message, index) => (
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
                builderView={builderView}
                isLastAssistantMessage={index === lastAssistantIndex}
                precedingUserQuery={
                  messages.slice(0, index).reverse().find((earlier) => earlier.role === 'user')?.content
                }
                onFollowUp={(text) => void sendMessage(text)}
                onRetry={(text) => void retryMessage(text)}
                onEditRequest={onEditRequest}
                onAuthenticate={onAuthenticate}
              />
            )}
          </motion.div>
        ))}
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
        <span className="ec-msg-user-dot" aria-hidden="true" />
        You, {relativeTime(message.timestamp)}
      </div>
      <div className="ec-msg-user-text">{message.content}</div>
    </div>
  )
}

interface AgentMessageProps {
  message: AgentChatMessage
  addToCart: PellierChatBodyProps['addToCart']
  builderView: boolean
  onFollowUp: (text: string) => void
  onRetry: (text: string) => void
  onEditRequest: (text: string) => void
  onAuthenticate: () => void
  isLastAssistantMessage: boolean
  /** The question this answer replies to, used to find the next scripted turn. */
  precedingUserQuery: string | undefined
}

function AgentMessage({
  message,
  addToCart,
  builderView,
  onFollowUp,
  onRetry,
  onEditRequest,
  onAuthenticate,
  isLastAssistantMessage,
  precedingUserQuery,
}: AgentMessageProps) {
  const reducedMotion = useReducedMotion()
  const streamDone = message.agentStatus === 'complete' || message.agentStatus === undefined
  const hasTurn = Boolean(message.status) || (message.steps?.length ?? 0) > 0
  // Only a turn opened in this session reveals; history shows at once.
  const instant = !message.live
  const [reveal, setReveal] = useState(() => ({
    length: instant ? message.content.length : 0,
    finished: instant,
  }))
  const onProgress = useCallback((length: number, finished: boolean) => {
    setReveal((current) =>
      current.length === length && current.finished === finished ? current : { length, finished },
    )
  }, [])
  const revealFinished = streamDone && reveal.finished
  const steps = message.steps ?? []

  const orderedProducts = message.products ? productsForRenderedProse(message.products, message.content) : []
  const recommendedProducts = orderedProducts.filter((product) => product.ownership !== 'owned')
  const ownedProducts = orderedProducts.filter((product) => product.ownership === 'owned')
  // Names and prices are emphasized as rendering over the revealed text. The
  // reveal paces the raw answer, so cards landing mid-reveal never rewind it.
  // Keyed on the names themselves, so a re-sorted list with the same names
  // keeps the same ranges.
  const emphasisKey = orderedProducts.map((product) => product.name).filter(Boolean).join('\u0000')
  const emphasis = useMemo(() => (emphasisKey ? emphasisKey.split('\u0000') : []), [emphasisKey])
  // A card appears once the sentence that names it has been revealed.
  const visibleProducts = recommendedProducts.filter((product) => {
    if (revealFinished) return true
    const end = sentenceEndAfter(message.content, product.name)
    return end >= 0 && reveal.length >= end
  })

  const statusState = message.failure ? 'failed' : message.status?.state ?? 'working'
  const statusLabel = message.failure
    ? 'Stopped before an answer'
    : message.status?.label ?? 'Sending your request'

  return (
    <div
      className="ec-msg-agent"
      aria-live={!streamDone ? 'polite' : undefined}
      aria-atomic={!streamDone ? 'false' : undefined}
    >
      <div className="ec-msg-agent-eyebrow">
        <PellierMark size={18} />
        Pellier
      </div>

      {/* Status and steps, from real stream events. The pulse stops when the
          turn completes or fails; the list folds once the answer has settled. */}
      {hasTurn && !revealFinished && <StatusLine label={statusLabel} state={statusState} />}
      {steps.length > 0 && (
        <StepList
          steps={steps}
          live={!streamDone}
          builderView={builderView}
          folded={revealFinished && !message.failure}
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

      {message.content && (
        <div className="ec-msg-body">
          <RevealedProse
            text={message.content}
            done={streamDone}
            instant={instant}
            flush={message.stopped}
            emphasis={emphasis}
            onProgress={onProgress}
          />
        </div>
      )}

      {/* Stylist handoff card: the answer is the handoff, so no product grid. */}
      {message.escalation && revealFinished && <StylistHandoffCard handoff={message.escalation} />}

      {/* Prepared, not carried out. The backend supplies the wording so no
          paraphrase can lose the guarantee. */}
      {message.reviewPending && revealFinished && (
        <div className="ec-review-pending" data-testid="pellier-review-pending" role="status">
          <p>{message.reviewPending.message}</p>
          {message.reviewPending.reviewId ? (
            <Link to={`/operator/reviews/${message.reviewPending.reviewId}`}>
              Open prepared request in Operator
            </Link>
          ) : null}
        </div>
      )}

      {visibleProducts.length > 0 && !message.reviewPending && (
        <div className="ec-artifacts">
          {visibleProducts.map((product, pIdx) => (
            <motion.div
              key={product.id || pIdx}
              initial={reducedMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={reducedMotion ? { duration: 0 } : { duration: 0.34, ease: 'easeOut' }}
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

      {ownedProducts.length > 0 && revealFinished && !message.reviewPending && (
        <section className="ec-owned-artifacts" aria-labelledby="collection-pieces-heading">
          <div id="collection-pieces-heading" className="ec-owned-artifacts-label">
            Already in your collection
          </div>
          <div className="ec-artifacts">
            {ownedProducts.map((product, pIdx) => (
              <motion.div
                key={product.id || pIdx}
                initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={reducedMotion ? { duration: 0 } : { duration: 0.34, ease: 'easeOut' }}
              >
                <ProductArtifactCard product={product} rankIndex={pIdx} onPrompt={(prompt) => onFollowUp(prompt)} />
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {revealFinished && isLastAssistantMessage && !message.failure && (
        <div className="ec-followups">
          {followupsForMessage(message, precedingUserQuery).map((chip) => (
            <button key={chip} type="button" className="ec-followup" onClick={() => onFollowUp(chip)}>
              {chip}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
