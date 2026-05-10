/**
 * WorkshopTelemetry — replays the WorkshopEvent stream for the Atelier
 * telemetry tab.
 *
 * Visual register aligned to ``docs/atelier_editorial_redesign.html``:
 *   - White panel cards with 1px ink-at-14% border, 10px radius
 *   - Tag pills use a mockup-matched cyan/amber/green ramp
 *     (200-fill / 800-text) with letter-spaced uppercase copy
 *   - SQL block bg cream-warm; keywords rendered in terracotta
 *     #c44536; numbers and ``$1`` placeholders in ink-soft; default
 *     identifiers inherit ink
 *   - Column headers letter-spaced uppercase 10px in ink-quiet,
 *     monospace cells in ink, dashed row separators
 *   - Meta footer italic ink-quiet with monospace inline-code spans
 *     rendered in ink-soft (font-style: normal)
 *   - Plan step states: RUNNING in terracotta letter-spaced caps,
 *     QUEUED in ink-quiet letter-spaced caps, OK in green
 *
 * The ``tag_class`` → color contract stays fixed so the backend
 * emitters don't change with this polish pass.
 */
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import type {
  WorkshopEvent,
  WorkshopPanelEvent,
  WorkshopPlanEvent,
  WorkshopStepEvent,
} from '../services/workshop'
import { usePersona } from '../contexts/PersonaContext'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM_WARM = '#f5e8d3'
const ACCENT = '#c44536'

// Persona-tailored empty-state subheads. When a returning persona is
// signed in, the empty state tells them what to ask so the first
// turn is grounded in their signal — Marco asks about linen + Lisbon,
// Anna asks about a gift under her ceiling, Theo asks about ceramics.
const EMPTY_PROMPT_BY_PERSONA: Record<string, string> = {
  marco:
    'Ask about linen for Lisbon, or something you saw last time. The bench will show every step.',
  anna:
    "Ask for a thoughtful gift under two hundred, or a milestone piece. The bench will show Pellier's reasoning.",
  theo:
    'Ask about stoneware that wears in, or linen throws. The bench will show how the storefront thinks.',
}

function emptyPromptFor(personaId: string): string {
  return (
    EMPTY_PROMPT_BY_PERSONA[personaId] ??
    'Every step appears here — the parse, the JOINs, the safety checks, the synthesis.'
  )
}

const PANEL_PREVIEW: Array<{
  tag: string
  pillBg: string
  pillFg: string
  description: string
  highlight?: boolean
}> = [
  { tag: 'LLM · HAIKU · INTENT',       pillBg: '#FAEEDA', pillFg: '#633806', description: 'parse the request' },
  { tag: 'TOOL REGISTRY · DISCOVER',    pillBg: '#E6F1FB', pillFg: '#0C447C', description: 'rank tools' },
  { tag: 'MEMORY · AGENTCORE · STM',    pillBg: '#E6F1FB', pillFg: '#0C447C', description: 'session context' },
  { tag: 'MEMORY · EPISODIC',           pillBg: '#EAF3DE', pillFg: '#27500A', description: 'recent orders' },
  { tag: 'MEMORY · PROFILE',            pillBg: '#EAF3DE', pillFg: '#27500A', description: 'preferences summary' },
  { tag: 'MEMORY · PROCEDURAL',         pillBg: '#EAF3DE', pillFg: '#27500A', description: 'cohort JOIN · the headline', highlight: true },
  { tag: 'MEMORY · SEMANTIC',           pillBg: '#EAF3DE', pillFg: '#27500A', description: 'pgvector search' },
  { tag: 'RECOMMENDATION · FILTER',     pillBg: '#E6F1FB', pillFg: '#0C447C', description: 'budget · category' },
  { tag: 'TOOL · CHECK_INVENTORY',      pillBg: '#EEEDFE', pillFg: '#3C3489', description: 'SQL · audit trail' },
  { tag: 'GUARDRAIL · FACT-CHECK',      pillBg: '#FAEEDA', pillFg: '#633806', description: 'verify picks' },
  { tag: 'GROUNDING',                   pillBg: '#EAF3DE', pillFg: '#27500A', description: 'cite every claim' },
  { tag: 'MEMORY · CONFIDENCE',         pillBg: '#EAF3DE', pillFg: '#27500A', description: 'deterministic from data' },
  { tag: 'LLM · OPUS · SYNTHESIZE',     pillBg: '#FAEEDA', pillFg: '#633806', description: 'grounded reply' },
]

// Mockup-matched panel tag ramp. Each family pairs a saturated fill
// with a deep text color so the pills read as chips rather than as
// background noise. ``cyan`` covers data operations (pgvector,
// Gateway, Memory, Tool Registry); ``amber`` covers LLM + Guardrail
// output; ``green`` covers grounding / success / confidence.
const TAG_COLORS: Record<
  'cyan' | 'amber' | 'green',
  { bg: string; border: string; fg: string }
> = {
  cyan:  { bg: '#B5D4F4', border: '#8EB8E2', fg: '#0C447C' },
  amber: { bg: '#F2DFA6', border: '#D9BF75', fg: '#664100' },
  green: { bg: '#C0DD97', border: '#8EB566', fg: '#27500A' },
}

const SQL_KEYWORDS =
  /\b(SELECT|FROM|WHERE|AND|OR|ORDER BY|LIMIT|JOIN|LEFT|INNER|ON|AS|GROUP BY|DESC|ASC|INSERT|INTO|VALUES|UPDATE|SET|RETURNING|WITH|BEGIN|COMMIT|CREATE|TABLE|INDEX|USING|EXTENSION|PRIMARY|KEY|NOT|NULL|DEFAULT|TRUE|FALSE|ANY|IN|COUNT|MAX|MIN|SUM|AVG)\b/g

/**
 * SQL syntax highlighter. Ports Coffee Roastery's kwify() with sentinel
 * tokens so keyword matches don't clash with HTML escaping. Output is
 * injected via dangerouslySetInnerHTML on a <pre> with no user content
 * (SQL comes from AgentContext emitters, not user input).
 *
 * Coloring:
 *   - keywords          → ACCENT terracotta
 *   - string literals   → ink-soft
 *   - $1 / $n           → ink-soft
 *   - cosine operators  → ink-soft bold
 *   - -- comments       → ink-quiet italic
 *   - default           → ink (inherited)
 */
function kwify(sql: string): string {
  // Markdown-safe sentinel pairs keep keyword matches from clashing
  // with HTML escaping. Each pair opens / closes a styled span.
  const S = {
    commentOpen:  '\x01', commentClose:  '\x02', // -- line comment (italic ink-quiet)
    literalOpen:  '\x03', literalClose:  '\x04', // 'str' and $N (ink-soft)
    keywordOpen:  '\x05', keywordClose:  '\x06', // SELECT / FROM / WHERE… (terracotta)
    operatorOpen: '\x07', operatorClose: '\x08', // <=> <-> <#> (terracotta bold)
  } as const

  let s = sql
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  s = s.replace(/--[^\n]*/g, (m) => `${S.commentOpen}${m}${S.commentClose}`)
  s = s.replace(/'[^']*'/g, (m) => `${S.literalOpen}${m}${S.literalClose}`)
  s = s.replace(/\$\d+/g, (m) => `${S.literalOpen}${m}${S.literalClose}`)
  s = s.replace(SQL_KEYWORDS, `${S.keywordOpen}$1${S.keywordClose}`)
  s = s.replace(
    /(&lt;=&gt;|&lt;-&gt;|&lt;#&gt;)/g,
    `${S.operatorOpen}$1${S.operatorClose}`,
  )
  s = s
    .replace(/\x01/g, `<span style="color:${INK_QUIET};font-style:italic">`)
    .replace(/\x02/g, '</span>')
    .replace(/\x03/g, `<span style="color:${INK_SOFT}">`)
    .replace(/\x04/g, '</span>')
    .replace(/\x05/g, `<span style="color:${ACCENT};font-weight:500">`)
    .replace(/\x06/g, '</span>')
    .replace(/\x07/g, `<span style="color:${ACCENT};font-weight:500">`)
    .replace(/\x08/g, '</span>')
  return s
}

function PanelCard({ ev }: { ev: WorkshopPanelEvent }) {
  const colors = TAG_COLORS[ev.tag_class] || TAG_COLORS.cyan
  return (
    <article
      className="rounded-[10px] animate-[fadeSlide_0.32s_ease-out] overflow-hidden"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.14)',
      }}
      data-testid={`panel-card-${ev.tag}`}
    >
      {/* Header row — tag pill + title + duration */}
      <header className="flex items-center gap-2.5 px-5 py-[14px]">
        <span
          className="font-mono text-[10px] font-medium px-[9px] py-[3px] rounded whitespace-nowrap uppercase"
          style={{
            color: colors.fg,
            background: colors.bg,
            border: `1px solid ${colors.border}`,
            letterSpacing: '0.12em',
          }}
        >
          {ev.tag}
        </span>
        <span className="flex-1 text-[14px] font-medium" style={{ color: INK }}>
          {ev.title}
        </span>
        {ev.duration_ms > 0 && (
          <span
            className="font-mono text-[11px]"
            style={{ color: INK_QUIET }}
          >
            {ev.duration_ms}ms
          </span>
        )}
      </header>

      {/* Body — SQL block, results table, meta footer */}
      <div className="px-5 pb-[18px]">
        {ev.sql && (
          <pre
            className="font-mono text-[12px] leading-[1.7] rounded-md overflow-x-auto whitespace-pre-wrap break-words"
            style={{
              background: CREAM_WARM,
              color: INK,
              padding: '12px 14px',
              marginBottom: ev.columns.length > 0 || ev.meta ? '14px' : '0',
            }}
            dangerouslySetInnerHTML={{ __html: kwify(ev.sql) }}
          />
        )}
        {ev.columns.length > 0 && (
          <div className="font-mono text-[12px]">
            <div
              className="grid gap-2.5 py-1.5 text-[10px] uppercase"
              style={{
                gridTemplateColumns: `repeat(${ev.columns.length}, minmax(min-content, 1fr))`,
                color: INK_QUIET,
                letterSpacing: '0.14em',
                borderBottom: '1px solid rgba(45, 24, 16, 0.1)',
              }}
            >
              {ev.columns.map((c, i) => (
                <span key={i}>{c}</span>
              ))}
            </div>
            {ev.rows.map((row, rIdx) => (
              <div
                key={rIdx}
                className="grid gap-2.5 py-2 animate-[rowIn_0.22s_ease-out]"
                style={{
                  gridTemplateColumns: `repeat(${ev.columns.length}, minmax(min-content, 1fr))`,
                  borderBottom:
                    rIdx === ev.rows.length - 1
                      ? 'none'
                      : '1px solid rgba(45, 24, 16, 0.05)',
                  color: INK,
                  animationDelay: `${rIdx * 80}ms`,
                  animationFillMode: 'both',
                }}
              >
                {row.map((cell, cIdx) => (
                  <span key={cIdx} className="break-words overflow-wrap-anywhere">
                    {cell}
                  </span>
                ))}
              </div>
            ))}
          </div>
        )}
        {ev.meta && (
          <div
            className="text-[12px] leading-[1.7] italic"
            style={{
              color: INK_QUIET,
              marginTop: ev.columns.length > 0 ? '14px' : '0',
              paddingTop: ev.columns.length > 0 ? '12px' : '0',
              borderTop:
                ev.columns.length > 0
                  ? '1px solid rgba(45, 24, 16, 0.1)'
                  : 'none',
            }}
            dangerouslySetInnerHTML={{ __html: ev.meta }}
          />
        )}
      </div>
    </article>
  )
}

interface PlanState {
  event: WorkshopPlanEvent
  stepStates: Array<'queued' | 'active' | 'done'>
}

/**
 * Reduce the event list into render state. The replay is "already played"
 * by the time these events arrive, so step events are collapsed into
 * their final state against the matching plan.
 */
function usePlanReducer(events: WorkshopEvent[]): {
  plan: PlanState | null
  panels: WorkshopPanelEvent[]
} {
  return useMemo(() => {
    let plan: PlanState | null = null
    const panels: WorkshopPanelEvent[] = []
    for (const ev of events) {
      if (ev.type === 'plan') {
        plan = {
          event: ev,
          stepStates: ev.steps.map(() => 'queued'),
        }
      } else if (ev.type === 'step' && plan) {
        const stepEv = ev as WorkshopStepEvent
        if (stepEv.index >= 0 && stepEv.index < plan.stepStates.length) {
          plan.stepStates[stepEv.index] = stepEv.state
        }
      } else if (ev.type === 'panel') {
        panels.push(ev)
      }
    }
    return { plan, panels }
  }, [events])
}

function PlanCard({ plan }: { plan: PlanState }) {
  const colors = TAG_COLORS.cyan
  return (
    <article
      className="rounded-[10px] animate-[fadeSlide_0.32s_ease-out] overflow-hidden"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.14)',
      }}
      data-testid="plan-card"
    >
      <header className="flex items-center gap-2.5 px-5 py-[14px]">
        <span
          className="font-mono text-[10px] font-medium px-[9px] py-[3px] rounded uppercase"
          style={{
            color: colors.fg,
            background: colors.bg,
            border: `1px solid ${colors.border}`,
            letterSpacing: '0.12em',
          }}
        >
          PLAN
        </span>
        <span className="flex-1 text-[14px] font-medium" style={{ color: INK }}>
          {plan.event.title}
        </span>
        {plan.event.duration_ms > 0 && (
          <span className="font-mono text-[11px]" style={{ color: INK_QUIET }}>
            ~{plan.event.duration_ms}ms
          </span>
        )}
      </header>
      <ol className="m-0 list-none px-5 pb-2">
        {plan.event.steps.map((step, i) => {
          const state = plan.stepStates[i]
          const stateLabel =
            state === 'done' ? 'OK' : state === 'active' ? 'RUNNING' : 'QUEUED'
          const stateColor =
            state === 'done' ? TAG_COLORS.green.fg : state === 'active' ? ACCENT : INK_QUIET
          return (
            <li
              key={i}
              className="flex items-center justify-between py-[9px] text-[13px]"
              style={{
                borderTop: i === 0 ? 'none' : '1px solid rgba(45, 24, 16, 0.07)',
                color: state === 'queued' ? INK_SOFT : INK,
              }}
            >
              <div className="flex items-center gap-3">
                <span
                  className="font-mono text-[11px]"
                  style={{ color: INK_QUIET }}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{step}</span>
              </div>
              <span
                className="font-mono text-[10px] uppercase"
                style={{ color: stateColor, letterSpacing: '0.14em' }}
              >
                {stateLabel}
              </span>
            </li>
          )
        })}
      </ol>
    </article>
  )
}

export default function WorkshopTelemetry({ events }: { events: WorkshopEvent[] }) {
  const { plan, panels } = usePlanReducer(events)
  const { persona } = usePersona()
  const isSignedIn = !!persona && persona.id !== 'fresh'

  if (!events.length) {
    return (
      <div className="py-6 px-4">
        {/* Hero */}
        <div className="text-center max-w-[520px] mx-auto pt-6 pb-8">
          <div
            className="text-[10px] font-medium uppercase mb-4 inline-flex items-center gap-2 justify-center"
            style={{ color: ACCENT, letterSpacing: '0.22em' }}
          >
            The bench is set
            {/* Persona tag — colored avatar pill right of the eyebrow
                when signed in as Marco / Anna / Theo. Signals that
                the trace the user is about to see is theirs. */}
            {isSignedIn && (
              <span
                className="inline-flex items-center gap-1.5 ml-1"
                style={{
                  color: INK_QUIET,
                  fontSize: 9.5,
                  letterSpacing: '0.22em',
                }}
              >
                ·
                <span
                  aria-hidden
                  className="inline-flex items-center justify-center rounded-full"
                  style={{
                    width: 16,
                    height: 16,
                    background: persona!.avatar_color,
                    color: '#faf3e8',
                    fontFamily: 'Fraunces, serif',
                    fontStyle: 'italic',
                    fontSize: 9,
                  }}
                >
                  {persona!.avatar_initial}
                </span>
                as {persona!.display_name}
              </span>
            )}
          </div>
          <h2
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontStyle: 'italic',
              fontSize: 32,
              lineHeight: 1.15,
              margin: 0,
              color: INK,
              fontWeight: 400,
              letterSpacing: '-0.01em',
            }}
          >
            {isSignedIn
              ? `Ask Pellier, as ${persona!.display_name}.`
              : 'Ask Pellier a question.'}
          </h2>
          <p
            className="mt-4"
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontStyle: 'italic',
              fontSize: 15,
              color: INK_SOFT,
              lineHeight: 1.6,
            }}
          >
            {isSignedIn
              ? emptyPromptFor(persona!.id)
              : 'Every step appears here — the parse, the JOINs, the safety checks, the synthesis.'}
          </p>
        </div>

        {/* 13-panel preview */}
        <div className="max-w-[480px] mx-auto">
          <div className="flex items-center gap-3 mb-4">
            <span className="flex-1 h-px" style={{ background: 'rgba(45, 24, 16, 0.12)' }} />
            <span className="text-[10px] uppercase" style={{ color: INK_QUIET, letterSpacing: '0.18em' }}>
              Each turn produces 13 panels
            </span>
            <span className="flex-1 h-px" style={{ background: 'rgba(45, 24, 16, 0.12)' }} />
          </div>

          <div className="flex flex-col gap-1">
            {PANEL_PREVIEW.map((p, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-3 py-[7px] rounded"
                style={{
                  opacity: 0.5,
                  background: p.highlight ? 'rgba(196, 69, 54, 0.04)' : undefined,
                }}
              >
                <span className="font-mono text-[10px] min-w-[18px]" style={{ color: INK_QUIET }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span
                  className="text-[9px] font-medium uppercase whitespace-nowrap px-[7px] py-[2px] rounded-[3px]"
                  style={{
                    background: p.pillBg,
                    color: p.pillFg,
                    letterSpacing: '0.14em',
                  }}
                >
                  {p.tag}
                </span>
                <span className="text-[11px] italic" style={{ color: INK_QUIET }}>
                  {p.description}
                </span>
              </div>
            ))}
          </div>

          <div
            className="mt-6 text-center text-[12px] italic"
            style={{ color: INK_QUIET, lineHeight: 1.7 }}
          >
            Each panel lights up as it emits.
          </div>
        </div>
      </div>
    )
  }

  // Top-to-bottom cascade: plan card lands first with a soft fade,
  // then each telemetry panel fades in beneath it at a 120ms stagger
  // so the eye follows the agent's reasoning down the page. Each
  // panel still has its own inner `fadeSlide`/`rowIn` keyframe for
  // within-card reveal (sql rows, meta lines); the outer stagger
  // sequences the panels themselves.
  return (
    <motion.div
      className="flex flex-col gap-3"
      initial="hidden"
      animate="visible"
      variants={{
        visible: { transition: { staggerChildren: 0.12, delayChildren: 0.08 } },
      }}
    >
      {plan && (
        <motion.div
          variants={{
            hidden: { opacity: 0, y: 8 },
            visible: { opacity: 1, y: 0, transition: { duration: 0.36, ease: 'easeOut' } },
          }}
        >
          <PlanCard plan={plan} />
        </motion.div>
      )}
      {panels.map((ev, i) => (
        <motion.div
          key={i}
          variants={{
            hidden: { opacity: 0, y: 10 },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration: 0.32, ease: [0.2, 0.9, 0.3, 1.05] },
            },
          }}
        >
          <PanelCard ev={ev} />
        </motion.div>
      ))}
      {/* Inspector link — frozen audit view of the current session's
       * traces. Appears after a turn completes so attendees can open
       * the full waterfall in a dedicated page. Session id is read
       * from the storage key the workshop backend writes on each
       * persona switch. */}
      {panels.length > 0 && (
        <motion.div
          variants={{
            hidden: { opacity: 0 },
            visible: { opacity: 1, transition: { duration: 0.4, delay: 0.2 } },
          }}
          style={{
            marginTop: 14,
            paddingTop: 14,
            borderTop: '1px dashed rgba(45, 24, 16, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            fontFamily: 'JetBrains Mono, ui-monospace, monospace',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: INK_QUIET,
          }}
        >
          <span>{panels.length} panels · captured this turn</span>
          <Link
            to={`/inspector?session=${encodeURIComponent(
              (typeof localStorage !== 'undefined'
                ? localStorage.getItem('pellier-session-id')
                : '') ?? '',
            )}`}
            data-testid="telemetry-inspector-link"
            style={{
              color: ACCENT,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              letterSpacing: '0.12em',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.textDecoration = 'underline'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.textDecoration = 'none'
            }}
          >
            Open in Inspector <span aria-hidden>→</span>
          </Link>
        </motion.div>
      )}
    </motion.div>
  )
}
