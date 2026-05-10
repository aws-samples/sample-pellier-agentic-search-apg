/**
 * EvaluationsArchPage — Atelier · Architecture · Evaluations.
 *
 * Template A (mental-model) page matching
 * docs/atelier-evaluations-architecture.html:
 *
 *   - Title + subtitle + meta strip (three axis summary counts)
 *   - The mental model: triangle SVG + three corner explainers
 *   - How to measure: three axis cards (truth / taste / telemetry)
 *     with meter bars, test method, common failures
 *   - The tradeoffs: three-column "two pass, one fail" grid
 *   - Cheat sheet: score apart / method match / shape matters
 *   - Live strip: three-score result panel with delta arrows
 *
 * Data sources — this page is aspirational. No evaluation harness ships
 * with Pellier today. All numbers are illustrative stubs drawn from the
 * mockup. The page makes this explicit via the LiveStrip stub caption
 * so participants never mistake demo numbers for measurement. The
 * shape of the stub data is chosen so a real harness could populate it
 * from a ``/api/atelier/evaluations`` endpoint later.
 */
import { useEffect, useState } from 'react'
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  LiveStrip,
} from '../atelier'
import '../../styles/atelier-arch.css'

interface PerformanceAggregates {
  turn_count: number
  empty: boolean
  layers_p50?: Record<string, number>
  total_p50?: number
  ttft_p50?: number
}

/**
 * usePerformanceAggregates — read /api/performance/runtime once so
 * the Telemetry axis can surface real p50s instead of the stub
 * percentages. Kept narrow: this page only needs totals for the
 * detail rows; the richer histogram/per-layer view lives on the
 * Performance tab itself.
 */
function usePerformanceAggregates(): PerformanceAggregates | null {
  const [agg, setAgg] = useState<PerformanceAggregates | null>(null)
  useEffect(() => {
    let alive = true
    fetch('/api/performance/runtime')
      .then(r => r.json())
      .then(d => {
        if (alive && d && typeof d === 'object') setAgg(d as PerformanceAggregates)
      })
      .catch(() => {
        /* quiet */
      })
    return () => {
      alive = false
    }
  }, [])
  return agg
}

// ---------------------------------------------------------------------------
// Stub evaluation data — shaped as a future /api/atelier/evaluations payload.
// ---------------------------------------------------------------------------

type Axis = 'truth' | 'taste' | 'telemetry'

interface AxisScore {
  axis: Axis
  pass_count: number
  total: number
  meter_pct: number
  delta: number | null // null = flat; sign = direction
  status: 'pass' | 'watch' | 'fail'
  detail: Array<{ label: string; value: string }>
}

interface EvalRunStub {
  total_cases: number
  ran_at: string // "11:42"
  duration: string // "6m 18s"
  commit: string // "main @ 8a4f2c"
  axes: Record<Axis, AxisScore>
}

const STUB_RUN: EvalRunStub = {
  total_cases: 240,
  ran_at: '11:42',
  duration: '6m 18s',
  commit: 'main @ 8a4f2c',
  axes: {
    truth: {
      axis: 'truth',
      pass_count: 226,
      total: 240,
      meter_pct: 94,
      delta: 1.2,
      status: 'pass',
      detail: [
        { label: 'Pricing facts', value: '98%' },
        { label: 'Stock claims', value: '91%' },
        { label: 'Policy answers', value: '96%' },
      ],
    },
    taste: {
      axis: 'taste',
      pass_count: 187,
      total: 240,
      meter_pct: 78,
      delta: -2.4,
      status: 'watch',
      detail: [
        { label: 'Editorial voice', value: '82%' },
        { label: 'Restraint', value: '71%' },
        { label: 'Product framing', value: '81%' },
      ],
    },
    telemetry: {
      axis: 'telemetry',
      pass_count: 88,
      total: 100,
      meter_pct: 88,
      delta: null,
      status: 'pass',
      detail: [
        { label: 'p50 within budget', value: '94%' },
        { label: 'p95 within budget', value: '82%' },
        { label: 'Cost / turn', value: '$0.018' },
      ],
    },
  },
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function EvaluationsArchPage() {
  const perf = usePerformanceAggregates()
  // Telemetry axis swaps its 'p50 within budget' detail line to live
  // numbers when the performance_log buffer has seen turns this
  // session. Truth and taste remain stub percentages — a real eval
  // harness is out of scope for this commit series.
  const run: EvalRunStub = (() => {
    if (!perf || perf.empty) return STUB_RUN
    const liveTotal = Math.round(perf.total_p50 ?? 0)
    const liveTtft = Math.round(perf.ttft_p50 ?? 0)
    return {
      ...STUB_RUN,
      total_cases: STUB_RUN.total_cases,
      axes: {
        ...STUB_RUN.axes,
        telemetry: {
          ...STUB_RUN.axes.telemetry,
          detail: [
            { label: 'p50 total', value: `${liveTotal}ms · live` },
            { label: 'p50 first token', value: `${liveTtft}ms` },
            { label: 'Turns observed', value: `${perf.turn_count}` },
          ],
        },
      },
    }
  })()

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'Evaluations']}
      title={
        <>
          Evaluations, <em>three kinds of right.</em>
        </>
      }
      subtitle={
        <>
          An agent's reply can be wrong in three different ways.{' '}
          <em>Truth</em> — did it get the facts right.{' '}
          <em>Taste</em> — did it sound like the boutique.{' '}
          <em>Telemetry</em> — did the system stay healthy. Three orthogonal
          axes; an agent passing all three is hard, and worth measuring
          separately.
        </>
      }
      meta={[
        { label: 'Truth', value: `${run.axes.truth.meter_pct}% pass` },
        { label: 'Taste', value: `${run.axes.taste.meter_pct}% pass` },
        { label: 'Telemetry', value: `${run.axes.telemetry.meter_pct}% pass` },
        { label: 'Last run', value: `${run.ran_at} · ${run.total_cases} cases` },
      ]}
    >
      {/* ---- The mental model ---- */}
      <SectionFrame
        eyebrow="The mental model"
        title={
          <>
            Truth, taste, <em>telemetry.</em>
          </>
        }
        description="Three corners, three failure modes, three test methods. The agent can be factually correct and still off-brand. It can sound right and still slow. Score them apart, then look at the shape together."
      >
        <div className="ev-tri-grid">
          <div className="ev-tri-svg-wrap">
            <svg
              className="ev-tri-svg"
              viewBox="0 0 380 280"
              xmlns="http://www.w3.org/2000/svg"
              aria-label="Evaluations triangle — truth, taste, telemetry"
            >
              {/* Frame */}
              <line x1="190" y1="50" x2="80" y2="220" stroke="var(--ink-5)" strokeWidth="1" />
              <line x1="190" y1="50" x2="300" y2="220" stroke="var(--ink-5)" strokeWidth="1" />
              <line x1="80" y1="220" x2="300" y2="220" stroke="var(--ink-5)" strokeWidth="1" />

              {/* TRUTH — top (green) */}
              <circle cx="190" cy="50" r="6" fill="var(--green-1)" />
              <text
                x="190"
                y="30"
                textAnchor="middle"
                className="ev-tri-label ev-tri-label-truth"
              >
                TRUTH
              </text>
              <text
                x="190"
                y="78"
                textAnchor="middle"
                className="ev-tri-sub"
              >
                facts
              </text>

              {/* TASTE — bottom-left (burgundy) */}
              <circle cx="80" cy="220" r="6" fill="var(--accent)" />
              <text
                x="80"
                y="245"
                textAnchor="middle"
                className="ev-tri-label ev-tri-label-taste"
              >
                TASTE
              </text>
              <text
                x="80"
                y="205"
                textAnchor="middle"
                className="ev-tri-sub"
              >
                voice
              </text>

              {/* TELEMETRY — bottom-right (amber) */}
              <circle cx="300" cy="220" r="6" fill="var(--amber-1)" />
              <text
                x="300"
                y="245"
                textAnchor="middle"
                className="ev-tri-label ev-tri-label-telemetry"
              >
                TELEMETRY
              </text>
              <text
                x="300"
                y="205"
                textAnchor="middle"
                className="ev-tri-sub"
              >
                health
              </text>

              {/* Center label */}
              <text
                x="190"
                y="158"
                textAnchor="middle"
                className="ev-tri-center"
              >
                right?
              </text>
              <line x1="167" y1="170" x2="213" y2="170" stroke="var(--accent)" strokeWidth="1" />

              {/* Shape overlay — a soft triangle offset from the corners
                  to suggest "score shape, not average". */}
              <polygon
                points="190,72 110,210 270,210"
                fill="rgba(196,69,54,0.08)"
                stroke="rgba(196,69,54,0.35)"
                strokeWidth="1"
              />
            </svg>
          </div>

          <div className="ev-tri-explainers">
            <CornerExplainer
              keyTag="CORNER · A"
              name="Truth."
              body={
                <>
                  Did the reply get the facts right? Was the price actually{' '}
                  <em>$148</em>? Was the Pellier actually{' '}
                  <em>in stock in size M</em>? Was the return policy{' '}
                  <em>actually 30 days</em>?
                </>
              }
              question='"If the customer fact-checked us, would we be embarrassed?"'
            />
            <CornerExplainer
              keyTag="CORNER · B"
              name="Taste."
              body={
                <>
                  Did the reply sound like the boutique? Editorial voice,
                  italic-serif products, no "I'd be happy to help!" — the{' '}
                  <em>Pellier register</em>. The hardest to score because
                  there's no ground truth.
                </>
              }
              question='"Could this line appear in any catalog, or only in ours?"'
            />
            <CornerExplainer
              keyTag="CORNER · C"
              name="Telemetry."
              body={
                <>
                  Did the system stay healthy? Time-to-first-token, total
                  latency, tool-call success rate, error rate, token cost
                  per turn. <em>Boring numbers</em> that stay boring when
                  things work.
                </>
              }
              question='"Would on-call sleep through this turn?"'
            />
          </div>
        </div>
      </SectionFrame>

      {/* ---- Three axis cards ---- */}
      <SectionFrame
        eyebrow="How to measure"
        title={
          <>
            Three axes, <em>three methods.</em>
          </>
        }
        description="Each axis needs its own evaluation harness. Truth tests against ground truth, taste against rubrics with LLM judging, telemetry against budgets. Mixing methods is the most common mistake."
      >
        <div className="ev-axes-grid">
          <AxisCard
            axis="truth"
            score={run.axes.truth}
            subtitle='"Are the facts correct?"'
            howWeTest={[
              <>
                Golden-set queries with <em>known</em> right answers
              </>,
              <>
                Fact-extraction comparison ·{' '}
                <span className="ev-mono">price, stock, policy</span>
              </>,
              <>Run nightly + on every PR to agents/tools</>,
              <>
                Failures bubble to <em>regressions</em>, not warnings
              </>,
            ]}
            commonFailures={[
              <>
                Stale tool data <em>(cache miss)</em>
              </>,
              <>Hallucinated stock for delisted SKUs</>,
              <>Wrong policy when policy doc updates</>,
            ]}
          />
          <AxisCard
            axis="taste"
            score={run.axes.taste}
            subtitle='"Does it sound like Pellier?"'
            howWeTest={[
              <>
                Rubric-based · <em>editorial voice, restraint, accuracy</em>
              </>,
              <>LLM judge with the rubric + few-shot examples</>,
              <>Sampled human review on 10% of cases</>,
              <>The number drifts more than truth — track the trend</>,
            ]}
            commonFailures={[
              <>"I'd be happy to help" filler creeping back in</>,
              <>
                Generic adjectives <em>(nice, great)</em>
              </>,
              <>Too many superlatives stacked</>,
            ]}
          />
          <AxisCard
            axis="telemetry"
            score={run.axes.telemetry}
            subtitle='"Did the system stay healthy?"'
            howWeTest={[
              <>
                Per-layer budgets <em>(see Runtime page)</em>
              </>,
              <>p50, p95 tracked continuously</>,
              <>Budget breach = soft alert; sustained = page</>,
              <>Cost per turn rolled up daily</>,
            ]}
            commonFailures={[
              <>
                Cold-start outliers <em>(Bedrock)</em>
              </>,
              <>Tool timeouts on Aurora overload</>,
              <>
                Token budget creep <em>(skill loading)</em>
              </>,
            ]}
          />
        </div>
      </SectionFrame>

      {/* ---- Tradeoffs ---- */}
      <SectionFrame
        eyebrow="The tradeoffs"
        title={
          <>
            Two pass, <em>one fail.</em>
          </>
        }
        description="Real failures usually look like passing two corners while breaking one. The shape of the failure tells you what kind of fix to reach for."
      >
        <div className="ev-tradeoff-grid">
          <TradeoffCell
            versus={
              <>
                <span className="ev-to-a">truth</span> +{' '}
                <span className="ev-to-c">telemetry</span> · not{' '}
                <span className="ev-to-b">taste</span>
              </>
            }
            headline={
              <>
                <em>Right and fast,</em> but it sounds like a help center.
              </>
            }
            body={
              <>
                Facts correct, latency good, voice flat.{' '}
                <em>Taste failure</em>. Fix in <em>skills</em> — sharpen{' '}
                <em>style-advisor</em> or load it more reliably. Don't fix
                in agent prompts; that's where rigidity creeps in.
              </>
            }
          />
          <TradeoffCell
            versus={
              <>
                <span className="ev-to-b">taste</span> +{' '}
                <span className="ev-to-c">telemetry</span> · not{' '}
                <span className="ev-to-a">truth</span>
              </>
            }
            headline={
              <>
                <em>Beautiful and quick,</em> and quietly wrong.
              </>
            }
            body={
              <>
                Voice on point, performance fine, but the price was off or
                the stock was a fiction. <em>Truth failure</em>. Fix in{' '}
                <em>tools</em> — fresher data, tighter contracts, better
                fallbacks when the data is missing.
              </>
            }
          />
          <TradeoffCell
            versus={
              <>
                <span className="ev-to-a">truth</span> +{' '}
                <span className="ev-to-b">taste</span> · not{' '}
                <span className="ev-to-c">telemetry</span>
              </>
            }
            headline={
              <>
                <em>Right and on-brand,</em> and seven seconds late.
              </>
            }
            body={
              <>
                Reply lands beautifully, but the customer left.{' '}
                <em>Telemetry failure</em>. Fix in <em>runtime</em> —
                parallel tools, defer what can wait, route deterministically
                before reaching for Opus.
              </>
            }
          />
        </div>
      </SectionFrame>

      {/* ---- Cheat sheet ---- */}
      <CheatSheet
        eyebrow="When in doubt"
        title={
          <>
            Three rules <em>about evaluating.</em>
          </>
        }
        cells={[
          {
            key: 'SCORE APART',
            name: 'Don\u2019t average corners.',
            question: <em>"What's the overall score?"</em>,
            list: [
              <>One number hides the failure shape</>,
              <>
                87% on truth + 87% on taste is a different system from 99%
                + 75%
              </>,
              <>Always report all three, never their mean</>,
              <>
                <em>
                  Composite scores are how you ship regressions confidently
                </em>
              </>,
            ],
          },
          {
            key: 'METHOD MATCH',
            name: 'Test each axis its way.',
            question: <em>"Why not just ask the LLM?"</em>,
            list: [
              <>
                Truth wants <em>ground-truth comparison</em>
              </>,
              <>
                Taste wants <em>rubric + judge + sampling</em>
              </>,
              <>
                Telemetry wants <em>budgets + percentiles</em>
              </>,
              <>
                <em>One harness can't do all three; build three</em>
              </>,
            ],
          },
          {
            key: 'SHAPE MATTERS',
            name: 'Look at which corner failed.',
            question: <em>"Where do we fix this?"</em>,
            list: [
              <>
                Truth fail → <em>tools</em>
              </>,
              <>
                Taste fail → <em>skills</em>
              </>,
              <>
                Telemetry fail → <em>runtime</em>
              </>,
              <>
                <em>The corner tells you the layer</em>
              </>,
            ],
          },
        ]}
      />

      {/* ---- Live strip ---- */}
      <LiveStrip
        eyebrow="Live · last eval run"
        title={
          <>
            Three scores, <em>one shape.</em>
          </>
        }
        meta={
          <>
            {run.total_cases} cases · {run.ran_at} · {run.duration} ·{' '}
            {run.commit}
          </>
        }
        stubCaption="Demo data. No evaluation harness is wired to this page yet — numbers are illustrative."
      >
        <div className="ev-score-grid">
          <ScoreCell score={run.axes.truth} />
          <ScoreCell score={run.axes.taste} />
          <ScoreCell score={run.axes.telemetry} />
        </div>
      </LiveStrip>
    </DetailPageShell>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CornerExplainer({
  keyTag,
  name,
  body,
  question,
}: {
  keyTag: string
  name: string
  body: React.ReactNode
  question: string
}) {
  return (
    <div className="ev-tri-row">
      <div className="ev-tri-label-cell">
        <span className="ev-tri-key">{keyTag}</span>
        <span className="ev-tri-name">{name}</span>
      </div>
      <div className="ev-tri-text">
        {body}
        <span className="ev-tri-question">{question}</span>
      </div>
    </div>
  )
}

function AxisCard({
  axis,
  score,
  subtitle,
  howWeTest,
  commonFailures,
}: {
  axis: Axis
  score: AxisScore
  subtitle: string
  howWeTest: React.ReactNode[]
  commonFailures: React.ReactNode[]
}) {
  const corner = axis === 'truth' ? 'A' : axis === 'taste' ? 'B' : 'C'
  const meterLabel =
    axis === 'telemetry' ? 'within budget' : `${score.pass_count} / ${score.total}`
  return (
    <article className={`ev-axis-card ev-axis-${axis}`}>
      <header className={`ev-axis-head ev-axis-head-${axis}`}>
        <div className="ev-axis-key">CORNER · {corner}</div>
        <h3 className="ev-axis-name">
          {axis.charAt(0).toUpperCase() + axis.slice(1)}.
        </h3>
        <p className="ev-axis-question">{subtitle}</p>
      </header>
      <div className="ev-axis-body">
        <div className="ev-axis-meter">
          <div className="ev-meter-bar">
            <div
              className={`ev-meter-fill ev-meter-fill-${axis}`}
              style={{ width: `${score.meter_pct}%` }}
            />
          </div>
          <span className="ev-meter-label">
            <span className="ev-meter-num">{score.meter_pct}%</span> ·{' '}
            {meterLabel}
          </span>
        </div>

        <div className="ev-axis-section-label">How we test</div>
        <ul className="ev-axis-list">
          {howWeTest.map((item, i) => (
            <li key={`test-${i}`}>{item}</li>
          ))}
        </ul>

        <div className="ev-axis-section-label">Common failures</div>
        <ul className="ev-axis-list">
          {commonFailures.map((item, i) => (
            <li key={`fail-${i}`}>{item}</li>
          ))}
        </ul>
      </div>
    </article>
  )
}

function TradeoffCell({
  versus,
  headline,
  body,
}: {
  versus: React.ReactNode
  headline: React.ReactNode
  body: React.ReactNode
}) {
  return (
    <div className="ev-to-cell">
      <div className="ev-to-versus">{versus}</div>
      <div className="ev-to-headline">{headline}</div>
      <p className="ev-to-text">{body}</p>
    </div>
  )
}

function ScoreCell({ score }: { score: AxisScore }) {
  const tagClass =
    score.status === 'pass'
      ? 'ev-score-tag-pass'
      : score.status === 'watch'
        ? 'ev-score-tag-watch'
        : 'ev-score-tag-fail'
  const tagLabel =
    score.status === 'pass' ? 'Pass' : score.status === 'watch' ? 'Watch' : 'Fail'
  const axisLabel = score.axis.charAt(0).toUpperCase() + score.axis.slice(1)

  let deltaClass = 'ev-score-delta'
  let deltaText: React.ReactNode = '→ flat'
  if (score.delta !== null && score.delta !== 0) {
    const isUp = score.delta > 0
    deltaClass = `ev-score-delta ${isUp ? 'ev-score-delta-up' : 'ev-score-delta-down'}`
    deltaText = (
      <>
        {isUp ? '↑' : '↓'} {isUp ? '+' : ''}
        {score.delta} vs last run
      </>
    )
  } else if (score.delta === null) {
    deltaClass = 'ev-score-delta ev-score-delta-flat'
  }

  return (
    <div className="ev-score-cell">
      <div className="ev-score-head">
        <span className="ev-score-name">
          <em>{axisLabel}</em>
        </span>
        <span className={`ev-score-tag ${tagClass}`}>{tagLabel}</span>
      </div>
      <div className="ev-score-big">
        {score.meter_pct}%<span className="ev-score-out-of">/100</span>
      </div>
      <div className={deltaClass}>{deltaText}</div>
      <div className="ev-score-detail">
        {score.detail.map((row, i) => (
          <div key={i} className="ev-score-row">
            <span>{row.label}</span>
            <span className="ev-score-row-val">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
