/**
 * ChatDrawer — right-side chat drawer for the storefront.
 *
 * The storefront's only conversational surface. Slides in from the right at
 * 240ms ease-out; backdrop dims the storefront to 35%
 * espresso. Matches docs/storefront-hero-drawer.html State 3.
 *
 * Three entry points (all external — the drawer itself is passive):
 *   1. Floating CommandPill click → ``activeModal === 'drawer'``
 *   2. ⌘K shortcut → same (UIProvider routes to 'drawer' on storefront)
 *   3. Suggestion pill click → ``openDrawerWithQuery(text)``
 *
 * Mounts via ``createPortal(..., document.body)`` — mandatory because
 * the storefront header's ``backdrop-filter: blur(12px)`` creates a
 * containing block that traps ``position: fixed`` descendants (same
 * bug we hit with PersonaModal).
 *
 * Reuses ``useAgentChat`` for state, streaming, and persistence.
 * Observatory and Operator do not mount this component: their evidence and
 * operational workflows remain scoped to their own surfaces.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import {
  ArrowUp,
  ArrowDown,
  ChevronDown,
  LoaderCircle,
  MessageCircle,
  Trash2,
  X,
} from 'lucide-react'
import { useUI } from '../contexts/UIContext'
import { useLayout } from '../contexts/LayoutContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useOptionalAuth } from '../contexts/AuthContext'
import {
  useAgentChat,
  type AgentChatMessage,
} from '../hooks/useAgentChat'
import PellierChatBody from './PellierChatBody'
import PellierWelcome from './PellierWelcome'
import PersonaModal from './PersonaModal'
import StatusLines from './StatusLines'
import '../styles/chat-drawer.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FRESH_GREETING =
  "Welcome to Pellier. I'm your personal shopping concierge. Tell me what you're looking for and I'll find the right pieces for you."
const RETURNING_GREETING =
  "Welcome back. Tell me what you're looking for and I'll find the right pieces for you."

// ---------------------------------------------------------------------------
// Platform detection for keyboard hint
// ---------------------------------------------------------------------------

function detectMac(): boolean {
  if (typeof navigator === 'undefined') return false
  const uaData = (navigator as unknown as {
    userAgentData?: { platform?: string }
  }).userAgentData
  const platform = uaData?.platform ?? navigator.platform ?? ''
  return /mac|iphone|ipad|ipod/i.test(platform)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChatDrawer() {
  const { activeModal, closeModal, openModal, consumePendingQuery } = useUI()
  const { guardrailsEnabled } = useLayout()
  const { addToCart, cartOpen } = useCart()
  const { persona } = usePersona()
  const auth = useOptionalAuth()

  const isOpen = activeModal === 'drawer' && Boolean(persona) && !cartOpen
  const reducedMotion = useReducedMotion()
  const [isMac, setIsMac] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const followLatestRef = useRef(true)
  const previousTurnCount = useRef(0)
  const [showLatest, setShowLatest] = useState(false)

  useEffect(() => {
    setIsMac(detectMac())
  }, [])

  // First-turn greeting stays generic. Personal claims belong to the Aurora
  // profile context that the backend loads for a concrete shopper request.
  const initialMessages = useMemo<AgentChatMessage[]>(() => {
    const firstName = persona ? persona.display_name.split(' ')[0] : ''
    const h = new Date().getHours()
    const tod = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
    const content = persona && persona.id !== 'fresh'
      ? `${tod}, ${firstName}. ${RETURNING_GREETING}`
      : FRESH_GREETING
    return [
      {
        role: 'assistant',
        content,
        timestamp: new Date(),
      },
    ]
  }, [persona])

  // Read session ID for AgentCore STM hydration — same ID the backend
  // uses to scope the conversation namespace.
  const currentSessionId = (() => {
    try { return localStorage.getItem('pellier-session-id') ?? undefined }
    catch { return undefined }
  })()

  const {
    messages,
    inputValue,
    setInputValue,
    isLoading,
    sendMessage,
    retryMessage,
    clearChat,
  } = useAgentChat({
    mode: 'storefront',
    guardrailsEnabled,
    initialMessages,
    persistKey: 'pellier-drawer-storefront',
    sessionId: currentSessionId,
  })

  // Conversation, draft, and reading position belong to the current persona.
  const prevPersonaId = useRef(persona?.id ?? null)
  useEffect(() => {
    const currentId = persona?.id ?? null
    if (prevPersonaId.current !== currentId) {
      prevPersonaId.current = currentId
      clearChat(initialMessages)
      setInputValue('')
      followLatestRef.current = true
      setShowLatest(false)
    }
  }, [persona?.id, clearChat, initialMessages, setInputValue])

  // Turn count (user messages only)
  const turnCount = messages.filter(m => m.role === 'user').length

  // Focus input on open
  useEffect(() => {
    if (!isOpen) return
    openerRef.current = document.activeElement as HTMLElement
    const t = setTimeout(() => inputRef.current?.focus(), 50)
    return () => clearTimeout(t)
  }, [isOpen])

  // Return focus on close
  useEffect(() => {
    if (isOpen || cartOpen) return
    openerRef.current?.focus()
    openerRef.current = null
  }, [isOpen, cartOpen])

  // Keep a product question pending while the shopper chooses a scenario.
  // Run after the persona reset above so it cannot erase the seeded turn.
  // Closing the chooser cancels the question instead of replaying it later.
  // A pending query adds to the active thread. Storefront suggestions are
  // follow-on shopping questions, so clearing the conversation here silently
  // discarded the shopper's context.
  const hasConsumedRef = useRef(false)
  useEffect(() => {
    if (!isOpen) {
      hasConsumedRef.current = false
      if (activeModal !== 'drawer') consumePendingQuery()
      return
    }
    if (hasConsumedRef.current) return
    hasConsumedRef.current = true
    const seeded = consumePendingQuery()
    if (seeded) {
      void sendMessage(seeded)
    }
  }, [isOpen, activeModal, consumePendingQuery, sendMessage])

  // Follow the reply until the shopper scrolls back. A new question resumes
  // following; streamed chunks never pull someone away from earlier text.
  const scrollToLatest = useCallback((smooth = false) => {
    const body = bodyRef.current
    if (!body) return
    followLatestRef.current = true
    setShowLatest(false)
    body.scrollTo({ top: body.scrollHeight, behavior: smooth && !reducedMotion ? 'smooth' : 'instant' })
  }, [reducedMotion])

  useLayoutEffect(() => {
    if (!isOpen) return
    if (turnCount !== previousTurnCount.current) followLatestRef.current = true
    previousTurnCount.current = turnCount
    if (followLatestRef.current && turnCount > 0) scrollToLatest()
  }, [messages, isOpen, turnCount, scrollToLatest])

  useEffect(() => {
    if (!isOpen) return
    const content = contentRef.current
    if (!content || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      if (followLatestRef.current && turnCount > 0) scrollToLatest()
    })
    observer.observe(content)
    return () => observer.disconnect()
  }, [isOpen, turnCount, scrollToLatest])

  useEffect(() => {
    if (activeModal !== 'drawer' || cartOpen) return
    const previousOverflow = document.body.style.overflow
    const root = document.getElementById('root')
    const previousInert = root?.inert ?? false
    document.body.style.overflow = 'hidden'
    if (root) root.inert = true
    return () => {
      document.body.style.overflow = previousOverflow
      if (root) root.inert = previousInert
    }
  }, [activeModal, cartOpen])

  // Focus trap: Tab/Shift+Tab cycle within drawer
  const drawerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const el = drawerRef.current
    if (!el) return
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const focusable = Array.from(el.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])'
      )).filter(node => node.getClientRects().length > 0)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen])

  const handleKeyPress = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && !isLoading) {
        e.preventDefault()
        sendMessage()
      }
    },
    [isLoading, sendMessage],
  )

  const hasUserMessages = messages.some(m => m.role === 'user')
  const keycap = isMac ? '⌘K' : 'Ctrl+K'

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, 104)}px`
  }, [inputValue, isOpen])

  if (!persona) {
    return <PersonaModal open={activeModal === 'drawer' && !cartOpen} onClose={closeModal} closeOnSelect={false} />
  }

  return createPortal(
    <>
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="cd-backdrop"
            data-testid="chat-drawer-backdrop"
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.24 }}
            onClick={() => closeModal()}
          />

          {/* Drawer */}
          <motion.div
            ref={drawerRef}
            className="cd-drawer"
            data-testid="chat-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Chat with Pellier"
            initial={reducedMotion ? false : { x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={reducedMotion
              ? { duration: 0 }
              : { duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* Mobile drag handle (decorative) */}
            <div className="cd-drag-handle" aria-hidden />

            {/* Header */}
            <div className="cd-head">
              <div className="cd-head-stack">
                <h3 className="cd-head-title">
                  Ask <em>Pellier.</em>
                </h3>
                <div className="cd-head-meta">
                  {persona && persona.id !== 'fresh' && (
                    <>
                      <span className="cd-persona-mark">
                        <span
                          className="cd-persona-av"
                          style={{
                            background: persona.avatar_color,
                            color: '#F7F3EE',
                          }}
                        >
                          {persona.avatar_initial}
                        </span>
                        <span className="cd-persona-name">
                          {persona.display_name.split(' ')[0]}
                        </span>
                      </span>
                      <span className="cd-meta-sep">·</span>
                    </>
                  )}
                  <span>Your shopping concierge</span>
                </div>
              </div>
              <button
                type="button"
                className="cd-close"
                aria-label="Close drawer"
                onClick={() => closeModal()}
              >
                <X size={14} />
              </button>
            </div>

            {/* Three facts, three sources: scenario, verified identity, rail. */}
            <details className="cd-session-details">
              <summary>Scenario &amp; account details <ChevronDown size={14} aria-hidden="true" /></summary>
              <StatusLines messages={messages} />
              {auth?.isAuthenticated ? (
                <button type="button" className="cd-session-signin" onClick={auth.logout}>Sign out</button>
              ) : (
                <button type="button" className="cd-session-signin" onClick={() => openModal('auth')}>Sign in for account requests</button>
              )}
            </details>

            {/* Body */}
            <div className="cd-body" ref={bodyRef} onScroll={() => {
              const body = bodyRef.current
              if (!body) return
              const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 80
              followLatestRef.current = atBottom
              setShowLatest(!atBottom)
            }}>
              <div className="cd-messages" ref={contentRef}>
              {!hasUserMessages && (
                <PellierWelcome
                  persona={persona}
                  onSend={(text) => void sendMessage(text)}
                />
              )}
              {hasUserMessages && (
                <PellierChatBody
                  messages={messages}
                  sendMessage={sendMessage}
                  retryMessage={retryMessage}
                  onEditRequest={(text) => {
                    setInputValue(text)
                    window.requestAnimationFrame(() => inputRef.current?.focus())
                  }}
                  onAuthenticate={() => openModal('auth')}
                  addToCart={addToCart}
                  persona={persona}
                />
              )}
              </div>
            </div>

            {/* Footer */}
            <div className="cd-foot">
              {hasUserMessages && showLatest ? (
                <button className="cd-latest" type="button" onClick={() => scrollToLatest(true)}>
                  <ArrowDown size={14} aria-hidden="true" /> Latest reply
                </button>
              ) : null}
              <div className="cd-input-row">
                <textarea
                  ref={inputRef}
                  className="cd-input"
                  rows={1}
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={handleKeyPress}
                  aria-label="Message Pellier"
                  placeholder={
                    hasUserMessages
                      ? 'Continue the conversation…'
                      : "Tell Pellier what you're looking for…"
                  }
                  aria-describedby="cd-composer-hint"
                />
                <button
                  type="button"
                  className="cd-send"
                  disabled={!inputValue.trim() || isLoading}
                  aria-label={isLoading ? 'Pellier is responding' : 'Ask Pellier'}
                  title={isLoading ? 'Pellier is responding' : 'Ask Pellier'}
                  data-loading={isLoading}
                  onClick={() => sendMessage()}
                >
                  {isLoading ? (
                    <LoaderCircle size={16} aria-hidden="true" />
                  ) : (
                    <ArrowUp size={16} aria-hidden="true" />
                  )}
                </button>
              </div>
              <div className="cd-foot-meta">
                <span id="cd-composer-hint">
                  {isLoading ? 'Pellier is responding. You can draft your next question.' : 'Enter to send · Shift+Enter for a new line'}
                </span>
                <span className="cd-keyboard-hint">Esc to close</span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>

    {/* "Continue chat" pill — shows when drawer is closed but has
        an active conversation. Gives the user a way to reopen or clear
        the persisted storefront thread. */}
    <AnimatePresence>
      {!isOpen && hasUserMessages && (
        <motion.div
          data-testid="continue-chat-pill"
          initial={reducedMotion ? false : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.25, delay: 0.3 }}
          className="cd-continue-shell"
        >
          <button
            type="button"
            className="cd-continue-main"
            onClick={() => openModal('drawer')}
          >
            <MessageCircle size={16} aria-hidden="true" />
            <span>Continue chat</span>
            <span className="cd-continue-key">{keycap}</span>
          </button>
          <button
            type="button"
            className="cd-continue-clear"
            onClick={() => clearChat(initialMessages)}
            aria-label="Clear chat"
            title="Clear chat"
          >
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
    </>,
    document.body,
  )
}
