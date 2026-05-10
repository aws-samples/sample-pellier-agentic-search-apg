/**
 * InspectorPage — the `/inspector` route.
 *
 * Session-scoped, frozen-in-time view of agent reasoning. Reads
 * persisted workshop chat messages from localStorage and renders the
 * agent_execution payload for a given session id (`?session=<id>`).
 *
 * Contrast with `/workshop`, which hosts the *live* AgentReasoningTraces
 * side panel and listens for `agent-execution-complete` events as they
 * stream. The inspector does not listen — it is the audit view, so it
 * only reflects what was captured up to the point the user navigated
 * here (Audit A option (a) gate).
 *
 * Link origin: the Concierge modal's trace-ID footer in workshop mode
 * points here with the current session id.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Brain } from 'lucide-react'
import { resolveAgentType, AGENT_IDENTITIES } from '../utils/agentIdentity'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const CREAM = '#fbf4e8'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'

function loadWorkshopMessages(): AgentChatMessage[] {
  try {
    const saved = localStorage.getItem('pellier-concierge-atelier')
    if (!saved) return []
    const parsed = JSON.parse(saved)
    return parsed.map((msg: any) => ({
      ...msg,
      timestamp: new Date(msg.timestamp),
    }))
  } catch {
    return []
  }
}

function agentGradient(agent: string): string {
  return (
    AGENT_IDENTITIES[resolveAgentType(agent)]?.gradient ||
    'linear-gradient(135deg, #6b7280 0%, #4b5563 100%)'
  )
}

interface WaterfallStatus {
  otel_enabled: boolean
  reason?: string
}

export default function InspectorPage() {
  const [params] = useSearchParams()
  const requestedSession = params.get('session')
  const currentSession =
    typeof localStorage !== 'undefined'
      ? localStorage.getItem('pellier-session-id')
      : null

  const messages = useMemo(() => loadWorkshopMessages(), [])

  // Poll the backend waterfall endpoint once on mount to surface the
  // global OTEL health state — catches the broken-init case even when
  // no chat turn has run yet. See Bug 3 audit.
  const [waterfallStatus, setWaterfallStatus] = useState<WaterfallStatus | null>(null)
  useEffect(() => {
    let cancelled = false
    fetch('/api/traces/waterfall')
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return
        if (data.otel_enabled === false) {
          setWaterfallStatus({ otel_enabled: false, reason: data.reason })
        } else {
          setWaterfallStatus({ otel_enabled: true })
        }
      })
      .catch(() => {
        /* network failure is non-fatal for the inspector */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Per-execution OTEL failure (from the chat turn's agent_execution
  // payload) overrides the global signal for that card.
  const hasFailedExecution = messages.some(
    m => m.role === 'assistant' && m.agentExecution?.otel_enabled === false,
  )
  const showGlobalBanner =
    (waterfallStatus && !waterfallStatus.otel_enabled) || hasFailedExecution
  const globalBannerReason =
    (hasFailedExecution
      ? messages.find(
          m => m.role === 'assistant' && m.agentExecution?.otel_enabled === false,
        )?.agentExecution?.reason
      : waterfallStatus?.reason) ||
    'Telemetry unavailable — see docs/troubleshooting-otel.md for debugging steps.'

  // If the URL session doesn't match the current one, we still render the
  // persisted messages — the snapshot is frozen per-browser, so showing
  // whatever was captured for this session is the expected behavior. We
  // only flag the mismatch so the reader knows the trace isn't live.
  const sessionMismatch = Boolean(
    requestedSession && currentSession && requestedSession !== currentSession,
  )

  const executions = messages.filter(
    m => m.role === 'assistant' && m.agentExecution,
  )

  return (
    <div style={{ minHeight: '100vh', background: CREAM, color: INK }}>
      <header
        className="flex items-center justify-between px-6 py-5"
        style={{ borderBottom: `1px solid ${INK_QUIET}30` }}
      >
        <Link
          to="/atelier"
          className="inline-flex items-center gap-2 text-sm"
          style={{ color: INK_SOFT }}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to atelier
        </Link>
        <div
          className="inline-flex items-center gap-2 text-[11px] font-mono"
          style={{ color: INK_QUIET }}
        >
          <Brain className="h-3.5 w-3.5" />
          {requestedSession
            ? `session · ${requestedSession.slice(0, 12)}`
            : 'no session id'}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <h1
          className="text-3xl mb-2"
          style={{ fontFamily: "'Fraunces', serif", color: INK }}
        >
          Trace inspector
        </h1>
        <p className="text-sm mb-8" style={{ color: INK_SOFT }}>
          Frozen view of agent reasoning for the requested session. Live
          updates continue to flow inside the Concierge modal on
          <Link to="/atelier" className="underline mx-1" style={{ color: ACCENT }}>
            /atelier
          </Link>
          — the inspector only reflects what was captured when this page loaded.
        </p>

        {sessionMismatch && (
          <div
            className="rounded-lg px-4 py-3 mb-6 text-sm"
            style={{
              background: 'rgba(196, 69, 54, 0.08)',
              border: `1px solid ${ACCENT}40`,
              color: INK,
            }}
          >
            The requested session id differs from the active one. Showing the
            most recent persisted traces from this browser.
          </div>
        )}

        {showGlobalBanner && (
          <div
            className="rounded-lg px-4 py-3 mb-6 flex items-start gap-3"
            style={{
              background: 'rgba(217, 119, 6, 0.10)',
              border: '1px solid rgba(217, 119, 6, 0.45)',
              color: INK,
            }}
            data-testid="otel-banner"
          >
            <AlertTriangle
              className="h-5 w-5 flex-shrink-0 mt-0.5"
              style={{ color: '#b45309' }}
            />
            <div className="text-sm leading-relaxed">
              <strong style={{ color: '#92400e' }}>Telemetry unavailable.</strong>{' '}
              {globalBannerReason}
            </div>
          </div>
        )}

        {executions.length === 0 ? (
          <div
            className="rounded-xl px-6 py-12 text-center"
            style={{
              background: 'rgba(255, 255, 255, 0.5)',
              border: `1px solid ${INK_QUIET}30`,
            }}
          >
            <Brain
              className="h-8 w-8 mx-auto mb-3"
              style={{ color: INK_QUIET }}
            />
            <p className="text-sm" style={{ color: INK_SOFT }}>
              No agent executions captured yet. Ask a question in the Concierge
              on the workshop route to populate this inspector.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {executions.map((msg, idx) => {
              const exec = msg.agentExecution!
              if (exec.otel_enabled === false) {
                return (
                  <article
                    key={idx}
                    className="rounded-xl px-5 py-4 flex items-start gap-3"
                    style={{
                      background: 'rgba(217, 119, 6, 0.06)',
                      border: '1px solid rgba(217, 119, 6, 0.30)',
                    }}
                  >
                    <AlertTriangle
                      className="h-5 w-5 flex-shrink-0 mt-0.5"
                      style={{ color: '#b45309' }}
                    />
                    <div className="flex-1">
                      <p
                        className="text-xs font-mono mb-1"
                        style={{ color: INK_SOFT }}
                      >
                        {msg.timestamp instanceof Date
                          ? msg.timestamp.toLocaleTimeString()
                          : ''}
                      </p>
                      <p className="text-sm" style={{ color: INK }}>
                        Trace capture failed for this turn. Waterfall rendering
                        disabled.
                      </p>
                      <p
                        className="text-[11px] mt-1 leading-relaxed"
                        style={{ color: INK_SOFT }}
                      >
                        {exec.reason || globalBannerReason}
                      </p>
                    </div>
                  </article>
                )
              }
              return (
                <article
                  key={idx}
                  className="rounded-xl overflow-hidden"
                  style={{
                    background: 'rgba(255, 255, 255, 0.6)',
                    border: `1px solid ${INK_QUIET}30`,
                  }}
                >
                  <header
                    className="px-5 py-3 flex items-center justify-between"
                    style={{
                      borderBottom: `1px solid ${INK_QUIET}25`,
                      background: 'rgba(255, 255, 255, 0.3)',
                    }}
                  >
                    <span className="text-xs font-mono" style={{ color: INK_SOFT }}>
                      {msg.timestamp instanceof Date
                        ? msg.timestamp.toLocaleTimeString()
                        : ''}
                    </span>
                    <span className="text-[11px]" style={{ color: INK_QUIET }}>
                      {exec.agent_steps.length} steps ·{' '}
                      {exec.tool_calls.length} tool calls ·{' '}
                      {exec.total_duration_ms}ms
                    </span>
                  </header>

                  {msg.content && (
                    <p
                      className="px-5 py-3 text-sm"
                      style={{ color: INK, borderBottom: `1px solid ${INK_QUIET}20` }}
                    >
                      {msg.content}
                    </p>
                  )}

                  <div className="px-5 py-4 space-y-2">
                    {exec.agent_steps.map((step, si) => (
                      <div
                        key={si}
                        className="flex items-start gap-3 text-xs"
                      >
                        <span
                          className="px-2 py-0.5 rounded-full text-[10px] font-medium text-white flex-shrink-0"
                          style={{ background: agentGradient(step.agent) }}
                        >
                          {step.agent}
                        </span>
                        <span className="flex-1" style={{ color: INK }}>
                          {step.action}
                        </span>
                        {step.duration_ms > 0 && (
                          <span
                            className="font-mono text-[10px] flex-shrink-0"
                            style={{ color: INK_QUIET }}
                          >
                            {step.duration_ms}ms
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {exec.tool_calls.length > 0 && (
                    <div
                      className="px-5 py-3"
                      style={{
                        borderTop: `1px solid ${INK_QUIET}20`,
                        background: 'rgba(255, 255, 255, 0.25)',
                      }}
                    >
                      <p
                        className="text-[10px] uppercase tracking-wider mb-2"
                        style={{ color: INK_QUIET }}
                      >
                        Tool calls
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {exec.tool_calls.map((tc, ti) => (
                          <span
                            key={ti}
                            className="text-[11px] font-mono px-2 py-1 rounded"
                            style={{
                              background: 'rgba(45, 24, 16, 0.06)',
                              color: INK,
                            }}
                          >
                            {tc.tool}
                            {tc.duration_ms > 0 && (
                              <span style={{ color: INK_QUIET }}>
                                {' '}
                                · {tc.duration_ms}ms
                              </span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}
