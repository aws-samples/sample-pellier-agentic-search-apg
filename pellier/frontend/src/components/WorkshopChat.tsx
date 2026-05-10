/**
 * WorkshopChat — Atelier chat column on the /workshop left rail.
 *
 * Owns the submit loop, session state, scroll behavior, and customer
 * picker. Delegates the visual composition of each agent reply to
 * ``AssistantTurn`` and the Turn primitive from services/workshop.ts,
 * which categorizes each event bundle into plan / panels / products /
 * confidence / text.
 *
 * Flow:
 *   1. User picks a seeded customer or stays anonymous.
 *   2. User submits a query (text or quick-query chip).
 *   3. ``queryWorkshop()`` returns ``{session_id, events}``.
 *   4. The turn is stored as ``Turn`` and handed up to the right
 *      rail via ``onEvents`` so the telemetry tab replays the same
 *      stream.
 *   5. ``AssistantTurn`` composes plan chip + tool chips + text.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Send, Copy, Check } from 'lucide-react'
import {
  queryWorkshopStream,
  resumeWorkshop,
  eventsToTurn,
  type Turn,
  type WorkshopEvent,
} from '../services/workshop'
import CustomerCard from './atelier-chat/CustomerCard'
import UserMessage from './atelier-chat/UserMessage'
import AssistantTurn from './atelier-chat/AssistantTurn'
import QuickQueryChips from './atelier-chat/QuickQueryChips'

const INK = '#2d1810'
const INK_QUIET = '#a68668'
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'

// Seeded demo customers from scripts/migrations/002_workshop_seed.sql.
const DEMO_CUSTOMERS: Array<{ id: string; label: string; sublabel?: string }> = [
  { id: 'anonymous', label: 'Anonymous' },
  { id: 'CUST-MARCO', label: 'Marco', sublabel: 'returning · linen · 7 orders' },
  { id: 'CUST-ANNA', label: 'Anna', sublabel: 'gift-giver · 5 orders' },
  { id: 'CUST-FRESH', label: 'New visitor', sublabel: 'empty memory' },
]

const QUICK_QUERIES = [
  "what's low on stock right now?",
  'compare two mens shirts',
  'return policy?',
]

interface WorkshopChatProps {
  /**
   * Parent owns the event list so WorkshopTelemetry (rendered in a
   * sibling column) can subscribe to the same stream.
   */
  onEvents: (events: WorkshopEvent[]) => void
  /**
   * Fired whenever the session id or customer identity changes so the
   * Atelier's right-rail band can render the session id · customer
   * inline alongside its "ATELIER / TELEMETRY" kicker, without lifting
   * the state out of this component.
   */
  onSession?: (state: { sessionId: string | null; customerLabel: string }) => void
  /**
   * Fired when a citation pill / "view trace" / "Open in trace" link
   * is clicked. The parent scrolls the telemetry tab to the matching
   * panel and flashes a terracotta border on it. The ``traceRef`` is
   * either ``"plan"``, a panel ``tag`` ("TOOL REGISTRY · DISCOVER"),
   * or a citation ``ref`` ("trace 7") — the scroll-and-flash hook on
   * the parent resolves each shape to the matching DOM node.
   */
  onOpenTrace?: (traceRef: string) => void
}

export default function WorkshopChat({
  onEvents,
  onSession,
  onOpenTrace,
}: WorkshopChatProps) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [customerId, setCustomerId] = useState<string>('anonymous')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  // Tracks customer ids we've already auto-resumed so picking
  // someone, resetting, then picking them again doesn't re-fire the
  // resume unless the user explicitly hits "new session".
  const resumedCustomersRef = useRef<Set<string>>(new Set())

  const customer = useMemo(
    () => DEMO_CUSTOMERS.find((c) => c.id === customerId) ?? DEMO_CUSTOMERS[0],
    [customerId],
  )

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [turns, isLoading])

  useEffect(() => {
    onSession?.({ sessionId, customerLabel: customer.label })
  }, [sessionId, customer.label, onSession])

  function resetSession() {
    setSessionId(null)
    setTurns([])
    setError(null)
    onEvents([])
    resumedCustomersRef.current.clear()
  }

  function copyChat() {
    const text = turns
      .map((t) => {
        const parts: string[] = []
        parts.push(`> ${t.user_text}`)
        if (t.panels.length > 0) {
          parts.push(`  [${t.panels.length} panels: ${t.panels.map((p) => p.tag).join(', ')}]`)
        }
        if (t.assistant_text) parts.push(t.assistant_text)
        return parts.join('\n')
      })
      .join('\n\n---\n\n')
    const header = `Session: ${sessionId ?? 'none'} | Customer: ${customer.label}\n\n`
    navigator.clipboard.writeText(header + text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  // Auto-fire the welcome-back resume turn when the user picks a
  // seeded demo customer on a fresh session. Gated on: non-anonymous,
  // no prior session, no turns yet, and first time we've seen this
  // customer id this session. Teaching moment: attendees see the
  // MEMORY panels populate without typing anything.
  useEffect(() => {
    if (customerId === 'anonymous') return
    if (sessionId) return
    if (turns.length > 0) return
    if (resumedCustomersRef.current.has(customerId)) return
    if (isLoading) return

    resumedCustomersRef.current.add(customerId)
    const turnId = `resume-${Date.now()}`
    const resumeText = '(resumed session)'

    setTurns([
      {
        id: turnId,
        user_text: resumeText,
        assistant_text: null,
        panels: [],
        resumed: true,
      },
    ])
    setIsLoading(true)

    resumeWorkshop({ customer_id: customerId })
      .then((res) => {
        setSessionId(res.session_id)
        onEvents(res.events)
        const resolved = eventsToTurn(turnId, resumeText, res.events)
        setTurns([{ ...resolved, resumed: true }])
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
        setTurns((prev) =>
          prev.map((t) =>
            t.id === turnId
              ? { ...t, assistant_text: `Resume failed: ${msg}` }
              : t,
          ),
        )
      })
      .finally(() => setIsLoading(false))
  }, [customerId, sessionId, turns.length, isLoading, onEvents])

  async function submit(query: string) {
    const trimmed = query.trim()
    if (!trimmed || isLoading) return

    setInput('')
    setError(null)
    const turnId = `t-${Date.now()}`

    // Show the user message + a placeholder in-flight turn immediately
    // so the chat doesn't feel frozen while the request is in flight.
    setTurns((prev) => [
      ...prev,
      { id: turnId, user_text: trimmed, assistant_text: null, panels: [] },
    ])
    setIsLoading(true)

    try {
      const allEvents: WorkshopEvent[] = []

      const { session_id: sid } = await queryWorkshopStream(
        {
          query: trimmed,
          session_id: sessionId,
          customer_id: customerId === 'anonymous' ? null : customerId,
        },
        (ev) => {
          allEvents.push(ev)
          // Push incremental events to the telemetry tab
          onEvents([...allEvents])
          // Incrementally update the turn so chat chips appear live
          const partial = eventsToTurn(turnId, trimmed, allEvents)
          setTurns((prev) =>
            prev.map((t) => (t.id === turnId ? partial : t)),
          )
        },
      )
      setSessionId(sid)

      // Final resolved turn with all events
      const resolved = eventsToTurn(turnId, trimmed, allEvents)
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId ? resolved : t)),
      )
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId
            ? { ...t, assistant_text: `Error: ${msg}` }
            : t,
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      className="flex flex-col h-full rounded-xl overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.7)',
        border: `1px solid ${INK_QUIET}30`,
      }}
    >
      {/* Sticky section label — "ATELIER / CHAT". Mirrors the
          "ATELIER / TELEMETRY" band on the right card: same height,
          padding, border, and letter-spacing. The visual mirror is
          the affordance — no arrow is needed. */}
      <div
        className="flex items-center gap-3 px-5 py-[14px] text-[10px] uppercase font-medium"
        style={{
          background: CREAM_WARM,
          borderBottom: `1px solid ${INK_QUIET}20`,
          color: INK_QUIET,
          letterSpacing: '0.16em',
        }}
      >
        <span>Atelier / Chat</span>
        <span className="flex-1 h-[1px]" style={{ background: `${INK_QUIET}30` }} />
        {turns.length > 0 && (
          <button
            type="button"
            onClick={copyChat}
            title="Copy chat to clipboard"
            className="transition-opacity hover:opacity-70"
            style={{ color: copied ? '#27500A' : INK_QUIET }}
          >
            {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>

      {/* Scrolling turn list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
        <CustomerCard
          name={customer.label}
          sublabel={customer.sublabel}
          sessionId={sessionId}
          onReset={resetSession}
          disabled={isLoading}
        />

        {turns.length === 0 && (
          <>
            <div
              className="text-[13px] mt-3"
              style={{ color: INK_QUIET }}
            >
              Ask anything, or pick a suggestion below. Telemetry renders on the right.
            </div>
            {/* Pre-turn "try asking" strip — mirrors the post-turn
                strip so the chat pattern stays identical before and
                after the first question. Customer picker stays as
                its own row above the composer. */}
            <QuickQueryChips
              queries={QUICK_QUERIES}
              onPick={submit}
              disabled={isLoading}
            />
          </>
        )}

        {turns.map((t) => (
          <div key={t.id}>
            <UserMessage
              text={t.user_text}
              variant={t.resumed ? 'resumed' : 'default'}
            />
            <AssistantTurn turn={t} onOpenTrace={onOpenTrace} />
          </div>
        ))}

        {/* Post-turn "try asking" strip — same component as pre-turn
            above. Renders once the most-recent turn has resolved so
            the chat stays warm between questions. */}
        {turns.length > 0 && turns[turns.length - 1].assistant_text !== null && (
          <QuickQueryChips
            queries={QUICK_QUERIES}
            onPick={submit}
            disabled={isLoading}
          />
        )}

        {isLoading && (
          <div
            className="text-[13px] italic"
            style={{ color: INK_QUIET, paddingLeft: 2 }}
          >
            thinking…
          </div>
        )}
        {error && !isLoading && (
          <div
            className="text-[12px] font-mono px-3 py-2 rounded-md mt-2"
            style={{
              background: '#fef2f2',
              color: '#b91c1c',
              border: '1px solid #fecaca',
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* Customer picker row (pre-turn only). Quick-query pills
          moved inline into the scroll list via QuickQueryChips, so
          the bottom chrome stays thin and the "try asking" strip
          reads consistently before and after the first question. */}
      {turns.length === 0 && (
        <div
          className="px-5 py-3 flex items-center gap-2 flex-wrap"
          style={{ borderTop: `1px solid ${INK_QUIET}20` }}
        >
          <span
            className="text-[10px] uppercase"
            style={{ color: INK_QUIET, letterSpacing: '0.16em' }}
          >
            Shop as
          </span>
          <select
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            disabled={isLoading}
            className="text-[12px] rounded-md px-2 py-1 font-mono"
            style={{
              background: CREAM,
              border: `1px solid ${INK_QUIET}40`,
              color: INK,
            }}
          >
            {DEMO_CUSTOMERS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
                {c.sublabel ? ` · ${c.sublabel}` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit(input)
        }}
        className="flex items-center gap-2 px-5 py-3"
        style={{ borderTop: `1px solid ${INK_QUIET}20`, background: CREAM_WARM }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Pellier anything…"
          disabled={isLoading}
          className="flex-1 rounded-full px-4 py-[10px] text-[14px] outline-none"
          style={{
            background: 'white',
            color: INK,
            border: `1px solid ${INK_QUIET}40`,
          }}
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          aria-label="Send"
          className="flex items-center justify-center rounded-full h-8 w-8 transition-opacity hover:opacity-85 disabled:opacity-40"
          style={{ background: INK, color: CREAM }}
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  )
}
