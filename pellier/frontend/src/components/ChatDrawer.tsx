/**
 * ChatDrawer — right-side chat drawer for the storefront.
 *
 * Replaces the centered ConciergeModal on storefront routes. Slides in
 * from the right at 240ms ease-out; backdrop dims the storefront to 35%
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
 * The Atelier's ConciergeModal is unaffected by this component.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { useUI } from '../contexts/UIContext'
import { useLayout } from '../contexts/LayoutContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import {
  useAgentChat,
  type AgentChatMessage,
} from '../hooks/useAgentChat'
import BoutiqueChatBody from './BoutiqueChatBody'
import BoutiqueWelcome from './BoutiqueWelcome'
import '../styles/chat-drawer.css'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Persona-specific welcome greetings with personal touch.
// Each returning persona gets a warm callback to their interests.
// Fresh visitors get a clean, inviting intro.
const PERSONA_GREETINGS: Record<string, string> = {
  marco:
    "I remember you love natural fabrics and pieces that travel well. Last time you were eyeing linen — shall we pick up where you left off, or explore something new?",
  anna:
    "Always great to see you. I know you have an eye for thoughtful gifts and milestone pieces. Tell me who you're shopping for and I'll find something that lands.",
  theo:
    "Welcome back. I see you gravitate toward slow-craft pieces — ceramics, washed linen, things with patina. What are you looking for today?",
}

const FRESH_GREETING =
  "Welcome to Pellier. I'm Pellier — your personal shopping concierge. Tell me what you're looking for and I'll find the right pieces for you."

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
  const { addToCart } = useCart()
  const { persona } = usePersona()

  const isOpen = activeModal === 'drawer'
  const [isMac, setIsMac] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    setIsMac(detectMac())
  }, [])

  // Initial welcome message — persona-aware with personal touch
  const initialMessages = useMemo<AgentChatMessage[]>(() => {
    const firstName = persona ? persona.display_name.split(' ')[0] : ''
    const h = new Date().getHours()
    const tod = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
    const personaGreeting = persona?.id ? PERSONA_GREETINGS[persona.id] : null
    const content = personaGreeting
      ? `${tod}, ${firstName}. ${personaGreeting}`
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
    clearChat,
  } = useAgentChat({
    mode: 'storefront',
    guardrailsEnabled,
    initialMessages,
    persistKey: 'pellier-drawer-storefront',
    sessionId: currentSessionId,
  })

  // Clear the conversation when the persona changes so the new
  // persona's welcome screen and LTM context take effect immediately.
  const prevPersonaId = useRef(persona?.id ?? null)
  useEffect(() => {
    const currentId = persona?.id ?? null
    if (prevPersonaId.current !== currentId) {
      prevPersonaId.current = currentId
      clearChat(initialMessages)
    }
  }, [persona?.id, clearChat, initialMessages])

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
    if (isOpen) return
    openerRef.current?.focus()
    openerRef.current = null
  }, [isOpen])

  // Consume pending query (from suggestion pill click).
  //
  // Uses useLayoutEffect (not useEffect) so the pending query is
  // consumed and sendMessage fires BEFORE the browser paints the first
  // frame. This prevents a one-frame flicker where the empty-state
  // ("What can Pellier help you find today?") renders before the user
  // message appears. sendMessage adds the user message to state
  // synchronously (via setMessages) so the first visible paint already
  // shows the user bubble + the "thinking" placeholder.
  // When the drawer opens with a pending query (pill click), reset
  // the conversation to the greeting + new query so the user always
  // sees the personalized welcome above their question.
  const hasConsumedRef = useRef(false)
  useLayoutEffect(() => {
    if (!isOpen) {
      hasConsumedRef.current = false
      return
    }
    if (hasConsumedRef.current) return
    hasConsumedRef.current = true
    const seeded = consumePendingQuery()
    if (seeded) {
      // Reset to greeting then immediately fire the query.
      // Both use setMessages updater functions so React 18 batches
      // them — sendMessage's `prev` sees clearChat's result.
      // Result: greeting + user bubble appear on the same paint.
      clearChat(initialMessages)
      void sendMessage(seeded)
    }
  }, [isOpen, consumePendingQuery, sendMessage, clearChat, initialMessages])

  // Auto-scroll
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const el = scrollAreaRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (nearBottom) {
      const t = setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 50)
      return () => clearTimeout(t)
    }
  }, [messages, isOpen])

  // Focus trap: Tab/Shift+Tab cycle within drawer
  const drawerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const el = drawerRef.current
    if (!el) return
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const focusable = el.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
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
      if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
        e.preventDefault()
        sendMessage()
      }
    },
    [isLoading, sendMessage],
  )

  const hasUserMessages = messages.some(m => m.role === 'user')
  const keycap = isMac ? '⌘K' : 'Ctrl+K'

  return createPortal(
    <>
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="cd-backdrop"
            data-testid="chat-drawer-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.24 }}
            onClick={closeModal}
          />

          {/* Drawer */}
          <motion.div
            ref={drawerRef}
            className="cd-drawer"
            data-testid="chat-drawer"
            role="dialog"
            aria-label="Chat with Pellier"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.24, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* Mobile drag handle (decorative) */}
            <div className="cd-drag-handle" aria-hidden />

            {/* Header */}
            <div className="cd-head">
              <div className="cd-head-stack">
                <div className="cd-head-eyebrow">Concierge</div>
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
                  <span>
                    turn {String(turnCount).padStart(2, '0')}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="cd-close"
                aria-label="Close drawer"
                onClick={closeModal}
              >
                <X size={14} />
              </button>
            </div>

            {/* Body */}
            <div className="cd-body" ref={scrollAreaRef}>
              {!hasUserMessages && (
                <BoutiqueWelcome
                  persona={persona}
                  onSend={(text) => void sendMessage(text)}
                />
              )}
              {hasUserMessages && (
                <BoutiqueChatBody
                  messages={messages}
                  sendMessage={sendMessage}
                  addToCart={addToCart}
                  persona={persona}
                />
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Footer */}
            <div className="cd-foot">
              <div className="cd-input-row">
                <input
                  ref={inputRef}
                  type="text"
                  className="cd-input"
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder={
                    hasUserMessages
                      ? 'Continue the conversation…'
                      : "Tell Pellier what you're looking for…"
                  }
                  disabled={isLoading}
                />
                <button
                  type="button"
                  className="cd-send"
                  disabled={!inputValue.trim() || isLoading}
                  aria-label="Send"
                  onClick={() => sendMessage()}
                >
                  Ask
                </button>
              </div>
              <div className="cd-foot-meta">
                <span>Esc to close · {keycap} to focus</span>
                <span>Conversation persists this session</span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>

    {/* "Continue chat" pill — shows when drawer is closed but has
        an active conversation. Gives the user a way to reopen. */}
    <AnimatePresence>
      {!isOpen && hasUserMessages && (
        <motion.button
          data-testid="continue-chat-pill"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={{ duration: 0.25, delay: 0.3 }}
          onClick={() => openModal('drawer')}
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            zIndex: 39,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '999px',
            background: 'var(--ink)',
            color: 'var(--cream-warm)',
            border: 'none',
            cursor: 'pointer',
            fontFamily: 'var(--sans)',
            fontSize: '14px',
            fontWeight: 500,
            boxShadow: '0 4px 16px rgba(31, 20, 16, 0.2), 0 2px 6px rgba(31, 20, 16, 0.1)',
          }}
        >
          <span style={{ fontSize: '16px' }}>💬</span>
          Continue chat
          <span style={{ fontSize: '11px', opacity: 0.6, fontFamily: 'var(--mono)' }}>
            {keycap}
          </span>
        </motion.button>
      )}
    </AnimatePresence>
    </>,
    document.body,
  )
}
