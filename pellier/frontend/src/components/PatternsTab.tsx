/**
 * PatternsTab — Atelier teaching surface comparing the three
 * multi-agent patterns the codebase knows how to run:
 *
 *   Pattern I  · Agents-as-Tools  (Strands)
 *   Pattern II · Graph            (Strands GraphBuilder)
 *   Pattern III · Dispatcher + Specialist (deterministic)
 *
 * Renders three side-by-side cards with a consistent anatomy:
 *   - Roman numeral eyebrow in mono
 *   - Italic Fraunces title
 *   - "Shape" diagram line (ASCII-style)
 *   - LLM-call-count badge
 *   - Short bullet list of when-to-use / when-not-to
 *   - Plus the "Why Dispatcher for the Boutique?" monograph at the
 *     bottom — the one question the workshop audience always asks.
 *
 * The tab renders inside WorkshopPage's main zone; it has no
 * dependencies on the live telemetry or the event stream. The three
 * pattern cards are knowledge surfaces, not runnable demos — the
 * runnable demo IS the Atelier chat on the left.
 */

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const ACCENT = '#c44536'
const RULE_1 = 'rgba(45, 24, 16, 0.08)'

const FRAUNCES_STACK = 'Fraunces, Georgia, serif'
const INTER_STACK = 'Inter, system-ui, sans-serif'
const MONO_STACK = 'JetBrains Mono, ui-monospace, monospace'

interface Pattern {
  numeral: string
  id: string
  title: string
  subtitle: string
  shape: string
  llmCalls: string
  strands: string
  tint: string
  goodFor: string[]
  tradeoffs: string[]
  usedIn: 'Boutique' | 'Atelier' | 'Atelier (toggle)'
}

const PATTERNS: readonly Pattern[] = [
  {
    numeral: 'I',
    id: 'agents-as-tools',
    title: 'Agents-as-Tools',
    subtitle: 'Orchestrator + specialists, each specialist wrapped as @tool.',
    shape: 'Haiku orchestrator → @tool specialists (5) → reply',
    llmCalls: '2 per turn',
    strands: 'Agent, @tool',
    tint: '#EEEDFE',
    goodFor: [
      'Teaching the basic Strands vocabulary — Agent, @tool, BedrockModel.',
      'Routing that benefits from an LLM reading the whole question.',
      'Audiences who need to see the orchestrator paraphrase-and-call rhythm.',
    ],
    tradeoffs: [
      'Two LLM calls per turn — latency roughly doubles.',
      'Orchestrator paraphrase can swallow the specialist\'s voice.',
      'Opaque routing — hard to assert which specialist will land a query.',
    ],
    usedIn: 'Atelier (toggle)',
  },
  {
    numeral: 'II',
    id: 'graph',
    title: 'Graph',
    subtitle: 'Router node dispatches to specialist nodes via a DAG with conditional edges.',
    shape: 'Router node → 5 specialist nodes (conditional edges)',
    llmCalls: '1–2 per turn',
    strands: 'GraphBuilder, Graph',
    tint: '#E6F1FB',
    goodFor: [
      'Making routing decisions explicit — the graph IS the documentation.',
      'Scenarios where specialists need to fan out (inventory + pricing together).',
      'Teaching workflow composition and conditional edges as first-class primitives.',
    ],
    tradeoffs: [
      'More moving parts than Dispatcher — the graph is overhead if routing is deterministic.',
      'Conditional-edge functions add a layer to debug.',
      'Strands GraphBuilder is newer — SDK shape can shift between versions.',
    ],
    usedIn: 'Atelier (toggle)',
  },
  {
    numeral: 'III',
    id: 'dispatcher',
    title: 'Dispatcher + Specialist',
    subtitle: 'Keyword classifier picks one specialist deterministically; specialist replies.',
    shape: 'Keyword intent → one specialist → reply',
    llmCalls: '1 per turn',
    strands: 'Agent (factory per specialist)',
    tint: '#EAF3DE',
    goodFor: [
      'Production retail — shopper sees exactly one voice.',
      'Deterministic latency — one LLM call, no paraphrase cycle.',
      'Intents that match keywords cleanly (pricing / inventory / support / search / recommendation).',
    ],
    tradeoffs: [
      'Classifier has to be right — a wrong bucket routes to the wrong specialist.',
      'No cross-specialist composition — one reply at a time.',
      'Keyword regex needs maintenance as the vocabulary grows.',
    ],
    usedIn: 'Boutique',
  },
]

export default function PatternsTab() {
  return (
    <div className="flex flex-col gap-6 py-4">
      {/* Header */}
      <div className="max-w-[640px]">
        <div
          style={{
            fontFamily: MONO_STACK,
            fontSize: 10.5,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: ACCENT,
            fontWeight: 500,
            marginBottom: 12,
          }}
        >
          Three patterns · one workshop
        </div>
        <h2
          style={{
            fontFamily: FRAUNCES_STACK,
            fontStyle: 'italic',
            fontWeight: 400,
            fontSize: 30,
            lineHeight: 1.15,
            letterSpacing: '-0.01em',
            color: INK,
            margin: 0,
          }}
        >
          How Pellier routes a question.
        </h2>
        <p
          style={{
            fontFamily: FRAUNCES_STACK,
            fontStyle: 'italic',
            fontWeight: 600,
            fontSize: 15,
            lineHeight: 1.6,
            color: INK_SOFT,
            margin: '12px 0 0',
          }}
        >
          Strands exposes three shapes for the same job. Each one
          trades latency, determinism, and specialist voice differently.
          The workshop teaches all three — and uses each where it fits.
        </p>
      </div>

      {/* Three pattern cards */}
      <div
        className="grid gap-4"
        style={{
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        }}
      >
        {PATTERNS.map((p) => (
          <article
            key={p.id}
            data-testid={`pattern-card-${p.id}`}
            style={{
              background: CREAM,
              border: `1px solid ${RULE_1}`,
              borderRadius: 12,
              padding: '22px 22px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <header
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span
                style={{
                  fontFamily: MONO_STACK,
                  fontSize: 11,
                  letterSpacing: '0.22em',
                  textTransform: 'uppercase',
                  color: INK_QUIET,
                  fontWeight: 500,
                }}
              >
                Pattern {p.numeral}
              </span>
              <span
                style={{
                  fontFamily: MONO_STACK,
                  fontSize: 9,
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  fontWeight: 500,
                  padding: '3px 8px',
                  borderRadius: 999,
                  background: p.tint,
                  color: '#2d1810',
                }}
              >
                {p.usedIn}
              </span>
            </header>
            <h3
              style={{
                fontFamily: FRAUNCES_STACK,
                fontStyle: 'italic',
                fontWeight: 400,
                fontSize: 24,
                lineHeight: 1.15,
                color: INK,
                margin: 0,
              }}
            >
              {p.title}
            </h3>
            <p
              style={{
                fontFamily: INTER_STACK,
                fontSize: 13.5,
                lineHeight: 1.55,
                letterSpacing: '-0.003em',
                color: INK_SOFT,
                margin: 0,
              }}
            >
              {p.subtitle}
            </p>
            <div
              style={{
                background: CREAM_WARM,
                border: `1px solid ${RULE_1}`,
                borderRadius: 8,
                padding: '12px 14px',
                fontFamily: MONO_STACK,
                fontSize: 11,
                color: INK,
                lineHeight: 1.5,
              }}
            >
              {p.shape}
            </div>
            <div
              style={{
                display: 'flex',
                gap: 16,
                fontFamily: MONO_STACK,
                fontSize: 10,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: INK_QUIET,
              }}
            >
              <span>
                <span style={{ color: ACCENT }}>●</span>{' '}
                {p.llmCalls}
              </span>
              <span>
                <span style={{ color: 'rgba(45, 24, 16, 0.25)' }}>·</span>{' '}
                {p.strands}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <ChecklistBlock label="Good for" items={p.goodFor} />
              <ChecklistBlock label="Trade-offs" items={p.tradeoffs} muted />
            </div>
          </article>
        ))}
      </div>

      {/* Why Dispatcher for the Boutique — monograph */}
      <article
        data-testid="pattern-rationale-dispatcher"
        style={{
          background: CREAM,
          border: `1px solid ${RULE_1}`,
          borderRadius: 12,
          padding: '28px 32px 32px',
          marginTop: 8,
          maxWidth: 720,
        }}
      >
        <div
          style={{
            fontFamily: MONO_STACK,
            fontSize: 10.5,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: ACCENT,
            fontWeight: 500,
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span
            aria-hidden
            style={{
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: ACCENT,
            }}
          />
          The question we get asked
        </div>
        <h3
          style={{
            fontFamily: FRAUNCES_STACK,
            fontStyle: 'italic',
            fontWeight: 400,
            fontSize: 26,
            lineHeight: 1.2,
            letterSpacing: '-0.01em',
            color: INK,
            margin: 0,
          }}
        >
          Why did we choose Dispatcher for the Boutique?
        </h3>
        <div
          style={{
            marginTop: 18,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            fontFamily: INTER_STACK,
            fontSize: 15,
            lineHeight: 1.7,
            letterSpacing: '-0.003em',
            color: INK,
          }}
        >
          <p style={{ margin: 0 }}>
            <span
              style={{
                fontFamily: FRAUNCES_STACK,
                fontStyle: 'italic',
                fontWeight: 500,
                color: INK_SOFT,
              }}
            >
              The shopper is speaking to Pellier, not to an orchestrator.
            </span>{' '}
            Agents-as-Tools runs the specialist, then asks Haiku to
            summarise the specialist's output. That paraphrase cycle
            swallows the specialist's voice — a warm linen-shop reply
            becomes a generic "Here are some great options." Retail
            can't afford that.
          </p>
          <p style={{ margin: 0 }}>
            <span
              style={{
                fontFamily: FRAUNCES_STACK,
                fontStyle: 'italic',
                fontWeight: 500,
                color: INK_SOFT,
              }}
            >
              The latency budget is one LLM call.
            </span>{' '}
            Two calls reads as lag to a shopper; it's acceptable for
            a workshop audience watching the trace unfold, not for
            the front door of a boutique.
          </p>
          <p style={{ margin: 0 }}>
            <span
              style={{
                fontFamily: FRAUNCES_STACK,
                fontStyle: 'italic',
                fontWeight: 500,
                color: INK_SOFT,
              }}
            >
              Routing is deterministic.
            </span>{' '}
            Retail intents — pricing, inventory, support, search,
            recommendation — don't need an LLM to classify. Keywords
            + regex do it in microseconds, and the classifier is
            debuggable with a print statement.
          </p>
        </div>
      </article>
    </div>
  )
}

function ChecklistBlock({
  label,
  items,
  muted = false,
}: {
  label: string
  items: string[]
  muted?: boolean
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: MONO_STACK,
          fontSize: 9.5,
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
          color: muted ? INK_QUIET : ACCENT,
          fontWeight: 500,
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      <ul
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          margin: 0,
          padding: 0,
          listStyle: 'none',
        }}
      >
        {items.map((item, i) => (
          <li
            key={i}
            style={{
              fontFamily: INTER_STACK,
              fontSize: 13,
              lineHeight: 1.5,
              letterSpacing: '-0.003em',
              color: muted ? INK_SOFT : INK,
              display: 'flex',
              gap: 8,
            }}
          >
            <span
              aria-hidden
              style={{
                flexShrink: 0,
                marginTop: 6,
                width: 4,
                height: 4,
                borderRadius: '50%',
                background: muted ? INK_QUIET : ACCENT,
              }}
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
