/**
 * RuntimeArchPage — Atelier · Architecture · Runtime (Template B · Sequence)
 *
 * Matches docs/atelier-runtime-architecture.html:
 *   - Title / subtitle / meta strip (layers count, this-turn total,
 *     first-token, streamed)
 *   - Layer overview: eight cards (7 layers + 1 total in espresso fill)
 *   - Sequence: seven numbered steps with handoff blocks on the right
 *     showing → in: / → out: shapes
 *   - Cheat sheet: fast first / parallel / defer
 *   - Live strip: horizontal waterfall bar with legend + totals row
 *
 * Data sources:
 *   - Per-layer timing: localStorage "pellier-last-runtime-timing"
 *     written by useAgentChat on each ``runtime_timing`` SSE event.
 *     Until the backend ships that event, the page falls back to
 *     the stub values below and shows the demo-data caption.
 */
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  LiveStrip,
  MonoBlock,
} from '../atelier'
import { useRuntimeTiming, type RuntimeTiming } from './shared-catalog'
import '../../styles/atelier-arch.css'

// Stub timing used until the backend instrumentation lands. Numbers
// chosen to match the mockup so the page reads plausibly on first open.
const STUB_TIMING: RuntimeTiming = {
  layers: {
    fastpath: 12,
    intent: 78,
    skill_router: 287,
    orchestrator: 418,
    specialist: 1800,
    tools: 244,
    stream: 8,
  },
  ttft_ms: 412,
  total_ms: 2847,
  timestamp: 0,
}

// Budget lines shown in the layer cards — documented targets.
const LAYER_BUDGETS: Record<keyof RuntimeTiming['layers'], number> = {
  fastpath: 20,
  intent: 80,
  skill_router: 280,
  orchestrator: 420,
  specialist: 1800,
  tools: 280,
  stream: 80,
}

const LAYERS: Array<{
  num: string
  key: keyof RuntimeTiming['layers']
  name: string
  desc: string
}> = [
  { num: 'i.', key: 'fastpath', name: 'Fastpath.', desc: 'Greetings, thanks, meta — short-circuit before any LLM fires.' },
  { num: 'ii.', key: 'intent', name: 'Intent.', desc: 'Deterministic classifier. Routes to the right specialist.' },
  { num: 'iii.', key: 'skill_router', name: 'Skill router.', desc: 'One Haiku call. Decides which skills to inject.' },
  { num: 'iv.', key: 'orchestrator', name: 'Orchestrator.', desc: 'Haiku dispatcher. Picks a specialist, hands off.' },
  { num: 'v.', key: 'specialist', name: 'Specialist.', desc: 'Opus reasoning + tool calls. Where time mostly goes.' },
  { num: 'vi.', key: 'tools', name: 'Tools.', desc: 'Aurora reads, embeddings, registry calls.' },
  { num: 'vii.', key: 'stream', name: 'Stream.', desc: 'SSE close, session_state write, async LTM extract.' },
]

export default function RuntimeArchPage() {
  const live = useRuntimeTiming()
  const timing = live ?? STUB_TIMING
  const isStub = live === null

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'Runtime']}
      title={
        <>
          Runtime, <em>one turn end-to-end.</em>
        </>
      }
      subtitle="A single message arrives at the API. By the time the user sees a streamed reply, it has touched seven layers — fastpath, intent, router, orchestrator, specialist, tools, stream. Each layer has a budget. Each layer has a job."
      meta={[
        { label: 'Layers', value: 7 },
        { label: 'This turn', value: `${timing.total_ms}ms total` },
        { label: 'First token', value: `${timing.ttft_ms}ms` },
        { label: 'Streamed', value: `${timing.total_ms - timing.ttft_ms}ms` },
      ]}
    >
      {/* ---- Layer overview ---- */}
      <SectionFrame
        eyebrow="The layers"
        title={
          <>
            Seven surfaces, <em>one message.</em>
          </>
        }
        description="A trimmed view of where time goes. Most layers are fast — the budget is dominated by the specialist agent and the streaming reply. Knowing the budgets is half of knowing where to optimize."
      >
        <div className="rt-layer-grid">
          {LAYERS.map((layer) => {
            const actual = timing.layers[layer.key]
            const budget = LAYER_BUDGETS[layer.key]
            const overBudget = actual > budget * 1.2
            return (
              <article className="rt-layer-card" key={layer.key}>
                <div className="rt-layer-num">{layer.num}</div>
                <div className="rt-layer-name">
                  <em>{layer.name}</em>
                </div>
                <div className={`rt-layer-budget ${overBudget ? 'rt-layer-over' : ''}`}>
                  <span className="arch-num">~{budget}</span>ms
                </div>
                <div className="rt-layer-text">{layer.desc}</div>
              </article>
            )
          })}
          <article className="rt-layer-card rt-layer-card-total">
            <div className="rt-layer-num">total</div>
            <div className="rt-layer-name">
              <em>One turn.</em>
            </div>
            <div className="rt-layer-budget">
              <span className="arch-num">{(timing.total_ms / 1000).toFixed(1)}</span>s
            </div>
            <div className="rt-layer-text">
              First token at{' '}
              <span className="rt-layer-hl-mono">~{timing.ttft_ms}ms</span>
              ; rest streams.
            </div>
          </article>
        </div>
      </SectionFrame>

      {/* ---- Sequence ---- */}
      <SectionFrame
        eyebrow="The journey"
        title={
          <>
            Step by step, <em>handoff by handoff.</em>
          </>
        }
        description="Each step shows what the layer received and what it passed forward. Following the right column tells you the data shape at every seam — the truth of the runtime is the handoffs, not the implementations."
      >
        <div className="rt-seq-list">
          <RuntimeStep
            num="i."
            name={<em>Triage fastpath.</em>}
            layerTag="deterministic · 20ms"
            desc={
              <>
                The request lands at <code className="arch-mono">POST /api/chat/stream</code>.
                Before anything LLM fires, a regex pass checks for greetings,
                thanks, and meta-queries. If matched, a canned reply ships and
                the turn ends here. <em>No agent invocation.</em>
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> message{' '}
                <MonoBlock.Comment>· session</MonoBlock.Comment>
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> match?{' '}
                <MonoBlock.Comment>→ canned</MonoBlock.Comment>
              </MonoBlock>
            }
            elapsed={timing.layers.fastpath}
          />

          <RuntimeStep
            num="ii."
            name={<em>Intent classification.</em>}
            layerTag="deterministic · 80ms"
            desc={
              <>
                A small classifier (rules + small embedding) tags the message
                as <em>recommend</em>, <em>search</em>, <em>support</em>,{' '}
                <em>pricing</em>, or <em>inventory</em>. The tag prepends an{' '}
                <code className="arch-mono">[USE: …]</code> hint so the
                orchestrator can route deterministically rather than reasoning
                about routing.
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> message
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> intent{' '}
                <MonoBlock.Comment>+ hint</MonoBlock.Comment>
              </MonoBlock>
            }
            elapsed={timing.layers.intent}
          />

          <RuntimeStep
            num="iii."
            name={
              <>
                Skill <em>routing.</em>
              </>
            }
            layerTag="Haiku · 280ms"
            desc={
              <>
                One short Haiku call against the skill registry's descriptions.
                Returns a JSON list of skill names to load. The loaded skills
                are injected into the specialist's system prompt via a{' '}
                <code className="arch-mono">ContextVar</code> — the
                orchestrator itself doesn't carry skills.
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> message{' '}
                <MonoBlock.Comment>· skills.list()</MonoBlock.Comment>
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> RouterDecision
              </MonoBlock>
            }
            elapsed={timing.layers.skill_router}
          />

          <RuntimeStep
            num="iv."
            name={<em>Orchestrator.</em>}
            layerTag="Haiku · 420ms"
            desc={
              <>
                The dispatcher. Reads the intent hint, picks one of the five
                specialists, and hands off. <em>Doesn't reason about the answer</em> —
                that's the specialist's job. Cheap and fast on purpose.
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> hint + msg + STM
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> specialist.invoke()
              </MonoBlock>
            }
            elapsed={timing.layers.orchestrator}
          />

          <RuntimeStep
            num="v."
            name={<em>Specialist agent.</em>}
            layerTag="Opus · 1,800ms"
            desc={
              <>
                Opus reasoning, with the loaded skills appended to the base
                system prompt. Reads STM, may pull LTM, decides which tools
                to fire, composes the streaming reply. <em>Where the budget
                mostly goes</em> — and where the editorial voice gets shaped.
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> prompt + skills + ctx
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> SSE token stream
              </MonoBlock>
            }
            elapsed={timing.layers.specialist}
            elapsedLabel={`~${(timing.layers.specialist / 1000).toFixed(1)}s`}
          />

          <RuntimeStep
            num="vi."
            name={
              <>
                Tools, <em>through the gateway.</em>
              </>
            }
            layerTag="parallel · 280ms"
            desc={
              <>
                During step v, the specialist invokes one or more tools —
                usually <em>find_pieces</em>, <em>check_inventory</em>,{' '}
                <em>get_recommendations</em>. The Gateway routes calls; results
                return to the specialist mid-reasoning. Cost is wall-clock
                parallel with v.
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>in:</MonoBlock.Key> tool name + args
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>out:</MonoBlock.Key> typed result
              </MonoBlock>
            }
            elapsed={timing.layers.tools}
          />

          <RuntimeStep
            num="vii."
            name={<em>Stream close, session write.</em>}
            layerTag="sync · 80ms"
            layerTagAsync="async · LTM"
            desc={
              <>
                The SSE stream emits its <code className="arch-mono">complete</code>{' '}
                event. Synchronously: write the new turn back to{' '}
                <code className="arch-mono">session_state</code>. Asynchronously,
                in a background job: extract durable facts and upsert them into
                LTM via Aurora pgvector. <em>The next turn starts hot.</em>
              </>
            }
            handoff={
              <MonoBlock label="Handoff">
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>sync:</MonoBlock.Key> session.upsert()
                <br />
                <MonoBlock.Arrow>→</MonoBlock.Arrow>{' '}
                <MonoBlock.Key>async:</MonoBlock.Key> ltm.extract(){' '}
                <MonoBlock.Comment>background</MonoBlock.Comment>
              </MonoBlock>
            }
            elapsed={timing.layers.stream}
            isLast
          />
        </div>
      </SectionFrame>

      {/* ---- Cheat sheet ---- */}
      <CheatSheet
        eyebrow="When in doubt"
        title={
          <>
            Three rules <em>about latency.</em>
          </>
        }
        cells={[
          {
            key: 'FAST FIRST',
            name: 'Cheap layers up front.',
            question: <em>"Why classify before reasoning?"</em>,
            list: [
              'Fastpath catches greetings · ~20ms',
              'Intent classifier routes deterministically · ~80ms',
              'Each cheap layer that succeeds saves 1.8s of Opus',
              <>
                <em>Don't make the smart model decide what the small model can</em>
              </>,
            ],
          },
          {
            key: 'PARALLEL',
            name: 'Tools while reasoning.',
            question: <em>"Why don't tool calls stack?"</em>,
            list: [
              'Specialist invokes tools mid-stream',
              'Multiple tools fire concurrently when independent',
              'Wall-clock cost = max(tool latencies), not sum',
              <>
                <em>Sequential tool chains are a smell</em>
              </>,
            ],
          },
          {
            key: 'DEFER',
            name: 'Async what can wait.',
            question: <em>"What blocks the user vs runs after?"</em>,
            list: [
              'Reply streaming blocks · everything else doesn\'t',
              'LTM extraction · async',
              'Telemetry · async',
              <>
                <em>Time-to-first-token is the only number the user feels</em>
              </>,
            ],
          },
        ]}
      />

      {/* ---- Live waterfall ---- */}
      <LiveStrip
        title={
          <>
            The waterfall, <em>this turn.</em>
          </>
        }
        meta={`${timing.total_ms}ms total · ttft ${timing.ttft_ms}ms`}
        stubCaption={
          isStub
            ? '// demo data — per-layer runtime_timing SSE event not yet emitted by the backend'
            : undefined
        }
      >
        <WaterfallBar timing={timing} />
      </LiveStrip>
    </DetailPageShell>
  )
}


/* ---- Sequence step (shared shape used 7x) ---- */
function RuntimeStep({
  num,
  name,
  desc,
  layerTag,
  layerTagAsync,
  handoff,
  elapsed,
  elapsedLabel,
  isLast,
}: {
  num: string
  name: React.ReactNode
  desc: React.ReactNode
  layerTag: string
  layerTagAsync?: string
  handoff: React.ReactNode
  elapsed: number
  elapsedLabel?: string
  isLast?: boolean
}) {
  return (
    <div className={`rt-seq-step ${isLast ? 'rt-seq-step-last' : ''}`}>
      <div className="rt-seq-num-wrap">
        <div className="rt-seq-num">{num}</div>
        {!isLast && <div className="rt-seq-line" />}
      </div>
      <div className="rt-seq-content">
        <div className="rt-seq-name-row">
          <h3 className="rt-seq-name">{name}</h3>
          <span className="rt-seq-layer-tag">{layerTag}</span>
          {layerTagAsync && (
            <span className="rt-seq-layer-tag rt-seq-layer-tag-async">
              {layerTagAsync}
            </span>
          )}
        </div>
        <p className="rt-seq-desc">{desc}</p>
      </div>
      <div className="rt-seq-handoff-slot">
        {handoff}
        <div className="rt-seq-elapsed">
          <span className="arch-num">{elapsedLabel ?? `${elapsed}ms`}</span>
        </div>
      </div>
    </div>
  )
}

/* ---- The waterfall bar + legend + totals ---- */

const WATERFALL_SEGMENTS: Array<{
  key: keyof RuntimeTiming['layers']
  label: string
  color: string
}> = [
  { key: 'fastpath', label: 'i.', color: '#5a3528' },
  { key: 'intent', label: 'ii.', color: '#6b3d2a' },
  { key: 'skill_router', label: 'iii.', color: '#8a4030' },
  { key: 'orchestrator', label: 'iv.', color: '#a8423a' },
  { key: 'specialist', label: 'v + vi.', color: '#b85a4a' },
  { key: 'stream', label: 'vii.', color: '#1f1410' },
]

const LEGEND_LABELS: Record<keyof RuntimeTiming['layers'], string> = {
  fastpath: 'Triage',
  intent: 'Intent',
  skill_router: 'Skill router',
  orchestrator: 'Orchestrator',
  specialist: 'Specialist + tools',
  tools: 'Tools',
  stream: 'Stream close',
}

function WaterfallBar({ timing }: { timing: RuntimeTiming }) {
  // The "v + vi" bucket is specialist + tools since the two run in parallel
  // from a wall-clock perspective (tools fire while the specialist reasons).
  // We use specialist alone for the segment size to avoid double-counting.
  const segments = WATERFALL_SEGMENTS.map((s) => {
    const ms =
      s.key === 'specialist'
        ? timing.layers.specialist // tools run parallel, don't add
        : timing.layers[s.key]
    return { ...s, ms }
  })
  const total = segments.reduce((acc, s) => acc + s.ms, 0)

  return (
    <div className="rt-waterfall">
      <div className="rt-waterfall-bar">
        {segments.map((s) => {
          const pct = (s.ms / Math.max(total, 1)) * 100
          return (
            <div
              key={s.key}
              className="rt-waterfall-seg"
              style={{ background: s.color, flexBasis: `${pct}%` }}
              title={`${LEGEND_LABELS[s.key]} · ${s.ms}ms`}
            >
              <span className="rt-waterfall-seg-label">{s.label}</span>
            </div>
          )
        })}
      </div>

      <div className="rt-waterfall-legend">
        {[
          { key: 'fastpath', label: 'Triage', roman: 'i.', ms: timing.layers.fastpath, color: '#5a3528' },
          { key: 'intent', label: 'Intent', roman: 'ii.', ms: timing.layers.intent, color: '#6b3d2a' },
          { key: 'skill_router', label: 'Skill router', roman: 'iii.', ms: timing.layers.skill_router, color: '#8a4030' },
          { key: 'orchestrator', label: 'Orchestrator', roman: 'iv.', ms: timing.layers.orchestrator, color: '#a8423a' },
          { key: 'specialist', label: 'Specialist + tools', roman: 'v + vi.', ms: timing.layers.specialist + timing.layers.tools, color: '#b85a4a' },
          { key: 'stream', label: 'Stream close', roman: 'vii.', ms: timing.layers.stream, color: '#1f1410' },
        ].map((item) => (
          <div className="rt-waterfall-legend-item" key={item.key}>
            <span
              className="rt-waterfall-swatch"
              style={{ background: item.color }}
              aria-hidden
            />
            <span className="rt-waterfall-name">
              <em>{item.roman}</em> {item.label}
            </span>
            <span className="rt-waterfall-ms">{item.ms}ms</span>
          </div>
        ))}
      </div>

      <div className="rt-waterfall-totals">
        <div>
          <span className="rt-waterfall-total-label">First token at</span>{' '}
          <span className="rt-waterfall-total-value">{timing.ttft_ms}ms</span> ·
          stream completed at{' '}
          <span className="rt-waterfall-total-value">{timing.total_ms}ms</span>
        </div>
        <div className="rt-waterfall-epilogue">
          <MonoBlock.Arrow>→</MonoBlock.Arrow> session.upsert ✓ ·{' '}
          <MonoBlock.Arrow>⇢</MonoBlock.Arrow> ltm.extract
        </div>
      </div>
    </div>
  )
}
