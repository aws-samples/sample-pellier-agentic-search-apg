/**
 * ChatDrawer: Ask Pellier, docked beside the store.
 *
 * On desktop widths the panel is a 440px column fixed to the right edge
 * under the shared header, and the page reflows to leave it room (see the
 * `.pellier-stage` padding in chat-drawer.css). On phones it stacks under
 * the page: the element sits after `#root` in the document, so in flow it is
 * the last thing on the page, and opening it scrolls it into view.
 *
 * It is a panel, not a pop-over: no backdrop, no scroll lock, no focus trap.
 * Escape still closes it through UIContext's global handler.
 *
 * Three entry points (all external):
 *   1. The header's Ask Pellier button → ``activeModal === 'drawer'``
 *   2. ⌘K shortcut → same (UIProvider routes to 'drawer' on storefront)
 *   3. A question from the home ask bar → ``openDrawerWithQuery(text)``
 *
 * Mounts via ``createPortal(..., document.body)``. Reuses ``useAgentChat``
 * for state, streaming, and persistence. Operator does not mount it.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import {
  ArrowUp,
  ArrowDown,
  ChevronDown,
  MessageCircle,
  Square,
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
import PellierMark from './PellierMark'
import PellierWelcome from './PellierWelcome'
import PersonaModal from './PersonaModal'
import StatusLines from './StatusLines'
import { BuilderViewSwitch, useBuilderView, useSkillMode } from './turn'
import '../styles/chat-drawer.css'
import '../styles/turn.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FRESH_GREETING =
  "Welcome to Pellier. I'm your personal shopping concierge. Tell me what you're looking for and I'll find the right pieces for you."
const RETURNING_GREETING =
  "Welcome back. Tell me what you're looking for and I'll find the right pieces for you."

/** Below this width the panel stacks under the page instead of docking. */
const DOCK_MIN_WIDTH = 1080

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

function docksBesideStore(): boolean {
  if (typeof window === 'undefined') return true
  return window.innerWidth >= DOCK_MIN_WIDTH
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChatDrawer() {
  const { activeModal, closeModal, openModal, consumePendingQuery, setTurnRunning } = useUI()
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
    stopTurn,
    clearChat,
  } = useAgentChat({
    guardrailsEnabled,
    initialMessages,
    persistKey: 'pellier-drawer-storefront',
    sessionId: currentSessionId,
  })

  // The header's Ask Pellier dot pulses only while a turn runs.
  useEffect(() => {
    setTurnRunning(isLoading)
    return () => setTurnRunning(false)
  }, [isLoading, setTurnRunning])

  // Builder view and the on-demand skills flex: off by default, per browser.
  const [builderView, setBuilderView] = useBuilderView()
  const [skillMode, setSkillMode] = useSkillMode()

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

  // While docked, the page leaves the panel its column. On a phone the panel
  // is the last thing in the document, so opening it scrolls it into view.
  const drawerRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const root = document.documentElement
    if (isOpen) root.setAttribute('data-ask-docked', 'true')
    else root.removeAttribute('data-ask-docked')
    return () => root.removeAttribute('data-ask-docked')
  }, [isOpen])

  // Focus input on open, and bring a stacked panel on screen.
  useEffect(() => {
    if (!isOpen) return
    openerRef.current = document.activeElement as HTMLElement
    if (!docksBesideStore()) {
      drawerRef.current?.scrollIntoView({
        behavior: reducedMotion ? 'instant' : 'smooth',
        block: 'start',
      })
    }
    const t = setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 50)
    return () => clearTimeout(t)
  }, [isOpen, reducedMotion])

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
        <motion.aside
          ref={drawerRef}
          className="cd-drawer"
          data-testid="chat-drawer"
          aria-label="Ask Pellier"
          initial={reducedMotion ? false : { opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 24 }}
          transition={reducedMotion
            ? { duration: 0 }
            : { duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
        >
          {/* Header */}
          <div className="cd-head">
            <PellierMark size={28} className="cd-mark" />
            <div className="cd-head-stack">
              <h3 className="cd-head-title">Ask Pellier</h3>
              <div className="cd-head-meta">
                {persona && persona.id !== 'fresh' && (
                  <span className="cd-persona-mark">
                    <span
                      className="cd-persona-av"
                      style={{ background: persona.avatar_color }}
                    >
                      {persona.avatar_initial}
                    </span>
                    <span className="cd-persona-name">
                      {persona.display_name.split(' ')[0]}
                    </span>
                  </span>
                )}
                <span>Your shopping concierge</span>
              </div>
            </div>
            <BuilderViewSwitch
              builderView={builderView}
              onBuilderView={setBuilderView}
              skillMode={skillMode}
              onSkillMode={setSkillMode}
            />
            <button
              type="button"
              className="cd-close"
              aria-label="Close Ask Pellier"
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
                builderView={builderView}
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
                disabled={!isLoading && !inputValue.trim()}
                aria-label={isLoading ? 'Stop' : 'Ask Pellier'}
                title={isLoading ? 'Stop' : 'Ask Pellier'}
                data-loading={isLoading}
                onClick={() => (isLoading ? stopTurn() : sendMessage())}
              >
                {isLoading ? (
                  <Square size={11} fill="currentColor" aria-hidden="true" />
                ) : (
                  <ArrowUp size={16} aria-hidden="true" />
                )}
              </button>
            </div>
            <div className="cd-foot-meta">
              <span id="cd-composer-hint">
                {isLoading ? 'Looking through the collection. You can draft your next question.' : 'Enter to send, Shift+Enter for a new line'}
              </span>
              <span className="cd-keyboard-hint">Esc to close</span>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>

    {/* "Continue chat" pill — shows when the panel is closed but has
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
