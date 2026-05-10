/**
 * GroundingArchPage — Atelier · Architecture · Grounding · Approvals · Guardrails.
 *
 * Template E (hybrid — mental-model + queue + audit) matching
 * docs/atelier-grounding-architecture.html:
 *
 *   - Title + subtitle + meta strip (lanes count, this-turn status,
 *     pending approvals, last block time)
 *   - The gate hero: three parallel lanes (guardrails / approvals /
 *     grounding), each with a status pill, checks list, foot metadata,
 *     plus an inflow pill and a decision verdict box
 *   - Three rules detail: one card per lane with "what it checks" +
 *     "how it runs" sections
 *   - Approvals queue spotlight: amber-themed section with a grid of
 *     queued tool calls
 *   - Cheat sheet: parallel / fail closed / visible
 *   - Live audit strip: last-N turn lane checks with stamps, verdicts,
 *     durations
 *
 * Data sources — this page is aspirational. No gate exists in backend
 * today (guardrails are wired on individual agents; approvals and
 * grounding are not yet implemented as a turn-boundary check). All
 * numbers and rows are illustrative stubs drawn from the mockup. The
 * LiveStrip + queue both carry stub captions so attendees never
 * mistake demo data for measurement. The shape is chosen so a real
 * gate could populate the same payload later.
 */
import { useEffect, useState } from 'react'
import {
  DetailPageShell,
  SectionFrame,
  CheatSheet,
  LiveStrip,
} from '../atelier'
import '../../styles/atelier-arch.css'

// ---------------------------------------------------------------------------
// Live wiring — policy decisions from the Strands BeforeToolCallEvent
// hook (services/policy_hook.py). Each DENY/ALLOW the backend records
// surfaces as an "Approvals" row with a verdict that matches the lane's
// status vocabulary.
// ---------------------------------------------------------------------------

interface GuardrailDecision {
  timestamp_ms: number
  source: 'INPUT' | 'OUTPUT'
  action: string
  allowed: boolean
  violations: Array<{ type?: string; confidence?: string }>
  latency_ms?: number | null
  text_preview?: string | null
  mode?: string | null
}

function useLiveGuardrails(): GuardrailDecision[] {
  const [rows, setRows] = useState<GuardrailDecision[]>([])
  useEffect(() => {
    let alive = true
    const sessionId = (() => {
      try {
        return localStorage.getItem('pellier-session-id') ?? ''
      } catch {
        return ''
      }
    })()

    const pull = () => {
      const qs = sessionId
        ? `?session_id=${encodeURIComponent(sessionId)}&limit=10`
        : '?limit=10'
      fetch(`/api/guardrails/decisions${qs}`)
        .then(r => r.json())
        .then(d => {
          if (!alive) return
          if (Array.isArray(d?.decisions)) setRows(d.decisions as GuardrailDecision[])
        })
        .catch(() => {
          /* quiet */
        })
    }

    pull()
    const interval = setInterval(pull, 3000)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [])
  return rows
}

interface PolicyDecision {
  timestamp_ms: number
  tool_name: string
  action: string
  decision: 'ALLOW' | 'DENY'
  violations: Array<{ policy_id?: string; policy_name?: string; reason?: string }>
  matching_policies: string[]
  parameters: Record<string, unknown>
  tool_use_id?: string | null
}

function useLivePolicyDecisions(): PolicyDecision[] {
  const [rows, setRows] = useState<PolicyDecision[]>([])
  useEffect(() => {
    let alive = true
    const sessionId = (() => {
      try {
        return localStorage.getItem('pellier-session-id') ?? ''
      } catch {
        return ''
      }
    })()

    const pull = () => {
      const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}&limit=10` : '?limit=10'
      fetch(`/api/agentcore/policy/decisions${qs}`)
        .then(r => r.json())
        .then(d => {
          if (!alive) return
          if (Array.isArray(d?.decisions)) {
            setRows(d.decisions as PolicyDecision[])
          }
        })
        .catch(() => {
          // Quiet failure — the stub audit rows still render below.
        })
    }

    pull()
    const interval = setInterval(pull, 3000)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [])
  return rows
}

function formatStamp(ms: number): string {
  const d = new Date(ms)
  return d.toLocaleTimeString('en-US', { hour12: false })
}

// ---------------------------------------------------------------------------
// Stub data — shape chosen so a future /api/atelier/grounding endpoint
// could populate this directly.
// ---------------------------------------------------------------------------

type LaneKind = 'guardrails' | 'approvals' | 'grounding'
type LaneStatus = 'pass' | 'queued' | 'block'
type CheckMark = 'ok' | 'queued' | 'blocked'

interface LaneCheck {
  mark: CheckMark
  text: string
  em?: string // trailing italic suffix
}

interface Lane {
  kind: LaneKind
  number: string // "I" / "II" / "III"
  name: string
  tagline: string
  status: LaneStatus
  statusLabel: string
  checks: LaneCheck[]
  footLeft: { label: string; num?: string }
  footRight: string
}

const LANES: Lane[] = [
  {
    kind: 'guardrails',
    number: 'I',
    name: 'Guardrails.',
    tagline: 'Bedrock content checks on the LLM output.',
    status: 'pass',
    statusLabel: 'Pass',
    checks: [
      { mark: 'ok', text: 'No PII detected' },
      { mark: 'ok', text: 'No toxicity flags' },
      { mark: 'ok', text: 'On-topic', em: '(boutique scope)' },
      { mark: 'ok', text: 'No prompt injection signals' },
    ],
    footLeft: { label: 'ms', num: '42' },
    footRight: 'aws · bedrock',
  },
  {
    kind: 'approvals',
    number: 'II',
    name: 'Approvals.',
    tagline: 'Aurora-backed queue for state-changing tool calls.',
    status: 'queued',
    statusLabel: 'Queued',
    checks: [
      { mark: 'ok', text: '2 reads · auto-passed' },
      { mark: 'queued', text: 'place_order · awaiting user confirm' },
      { mark: 'ok', text: '0 prior denials this session' },
    ],
    footLeft: { label: 'queue depth', num: '1' },
    footRight: 'aurora · approvals',
  },
  {
    kind: 'grounding',
    number: 'III',
    name: 'Grounding.',
    tagline: 'Claim verification against ground truth.',
    status: 'pass',
    statusLabel: 'Pass',
    checks: [
      { mark: 'ok', text: '3 prices match catalog' },
      { mark: 'ok', text: 'Stock claims verified · in-stock × 3' },
      { mark: 'ok', text: 'Policy citations valid' },
      { mark: 'ok', text: 'No hallucinated SKUs' },
    ],
    footLeft: { label: 'ms', num: '28' },
    footRight: 'aurora · catalog',
  },
]

interface QueueItem {
  stamp: string
  tool: string
  args: string
  age: string
  ageUrgent?: boolean
  status: 'pending' | 'approved' | 'denied'
}

const QUEUE_ITEMS: QueueItem[] = [
  {
    stamp: '11:47:33',
    tool: 'place_order',
    args: '"3 items · $543 · ship to ZIP 11201"',
    age: '14s',
    ageUrgent: true,
    status: 'pending',
  },
  {
    stamp: '11:38:02',
    tool: 'restock',
    args: '"Pellier shirt · size M · qty 6"',
    age: '9m',
    status: 'approved',
  },
  {
    stamp: '11:24:51',
    tool: 'place_order',
    args: '"1 item · $185 · ship to ZIP 94110"',
    age: '22m',
    status: 'approved',
  },
  {
    stamp: '11:12:18',
    tool: 'cancel_order',
    args: '"order_4f8a · refund to original payment"',
    age: '35m',
    status: 'denied',
  },
]

interface AuditRow {
  stamp: string
  lane: LaneKind
  laneLabel: string
  verdict: 'pass' | 'block' | 'queued' | 'cleared'
  verdictLabel: string
  detail: React.ReactNode
  ms?: string // may be '—'
}

const AUDIT_ROWS: AuditRow[] = [
  {
    stamp: '11:47:33',
    lane: 'approvals',
    laneLabel: 'Approvals',
    verdict: 'queued',
    verdictLabel: 'Queued',
    detail: (
      <>
        place_order · <span className="gt-mono">$543</span> · awaiting confirm
      </>
    ),
    ms: '—',
  },
  {
    stamp: '11:47:32',
    lane: 'grounding',
    laneLabel: 'Grounding',
    verdict: 'pass',
    verdictLabel: 'Pass',
    detail: <>3 price claims, 3 stock claims · all match</>,
    ms: '28ms',
  },
  {
    stamp: '11:47:32',
    lane: 'guardrails',
    laneLabel: 'Guardrails',
    verdict: 'pass',
    verdictLabel: 'Pass',
    detail: <>no flags · 4 categories evaluated</>,
    ms: '42ms',
  },
  {
    stamp: '11:38:02',
    lane: 'approvals',
    laneLabel: 'Approvals',
    verdict: 'cleared',
    verdictLabel: 'Cleared',
    detail: <>restock · approved by user · 9m queue</>,
    ms: '—',
  },
  {
    stamp: '11:31:18',
    lane: 'guardrails',
    laneLabel: 'Guardrails',
    verdict: 'block',
    verdictLabel: 'Block',
    detail: <>PII detected · email in candidate reply · retried</>,
    ms: '38ms',
  },
  {
    stamp: '11:24:51',
    lane: 'approvals',
    laneLabel: 'Approvals',
    verdict: 'cleared',
    verdictLabel: 'Cleared',
    detail: <>place_order · approved by user · 22m queue</>,
    ms: '—',
  },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GroundingArchPage() {
  const liveDecisions = useLivePolicyDecisions()
  const liveGuardrails = useLiveGuardrails()

  // Live numbers: count DENY decisions as blocks, ALLOW as passes for
  // the Approvals lane's header meta. Keeping the other lanes' stub
  // numbers intact — guardrails and grounding wire in on separate
  // commits (11 and a future grounding instrumentation).
  const livePassCount = liveDecisions.filter((d) => d.decision === 'ALLOW').length
  const liveDenyCount = liveDecisions.filter((d) => d.decision === 'DENY').length

  const passCount = LANES.filter((l) => l.status === 'pass').length
  const queuedCount = LANES.filter((l) => l.status === 'queued').length
  const blockedCount = LANES.filter((l) => l.status === 'block').length + liveDenyCount

  return (
    <DetailPageShell
      crumb={['Atelier', 'Architecture', 'Grounding · Approvals · Guardrails']}
      title={
        <>
          The gate, <em>at the boundary.</em>
        </>
      }
      subtitle={
        <>
          Three checks fire at the same moment — the boundary between
          "agent finished thinking" and "user sees the answer." Bedrock
          guardrails on the LLM. Approvals queue for sensitive tool
          calls. Claim verification against ground truth. The answer
          leaves only if it survives every check.
        </>
      }
      meta={[
        { label: 'Lanes', value: '3 parallel' },
        {
          label: 'This turn',
          value: `${passCount} pass · ${queuedCount} queued`,
        },
        { label: 'Pending approvals', value: queuedCount },
        { label: 'Last block', value: '11:31 · guardrails' },
      ]}
    >
      {/* ---- Gate hero ---- */}
      <SectionFrame
        eyebrow="The mental model"
        title={
          <>
            Three lanes, <em>one boundary.</em>
          </>
        }
        description="The gate runs after the agent has composed a candidate reply but before the user sees it. Three independent lanes evaluate in parallel. Any single failure blocks the response. There is no partial pass."
      >
        <div className="gt-canvas">
          <div className="gt-canvas-header">
            <span className="gt-canvas-label">The gate · this turn</span>
            <span className="gt-canvas-meta">
              <span className="gt-canvas-num">{passCount}</span> pass ·{' '}
              <span className="gt-canvas-num">{queuedCount}</span> queued ·{' '}
              <span className="gt-canvas-num">{blockedCount}</span> blocked
            </span>
          </div>

          {/* Inflow pill */}
          <div className="gt-inflow">
            <div className="gt-inflow-pill">
              <span className="gt-inflow-label">CANDIDATE REPLY</span>
              <em>"three linen pieces around $200 + place_order tool call"</em>
            </div>
          </div>

          {/* Three lanes */}
          <div className="gt-lanes">
            {LANES.map((lane) => (
              <LaneCard key={lane.kind} lane={lane} />
            ))}
          </div>

          {/* Funnel + decision */}
          <div className="gt-funnel">
            <div className="gt-decision">
              <span className="gt-verdict">
                <em>Held.</em>
              </span>
              <span className="gt-verdict-rule" aria-hidden />
              <span className="gt-conditions">
                <em>Awaiting</em> approval on place_order. Reply ships once
                the customer confirms.
              </span>
            </div>
          </div>

          <p className="gt-foot-caption">
            <em>The answer leaves only if it survives every lane.</em> One
            queued check holds the whole turn until cleared.
          </p>
        </div>
      </SectionFrame>

      {/* ---- Three rules detail ---- */}
      <SectionFrame
        eyebrow="The three lanes"
        title={
          <>
            What each one <em>actually checks.</em>
          </>
        }
        description="Independent lanes need independent contracts. Guardrails check the prose; approvals check the actions; grounding checks the facts. Mixing them is the most common implementation mistake."
      >
        <div className="gt-rd-grid">
          <RuleDetailCard
            kind="guardrails"
            number="I"
            name="Guardrails."
            tagline="Bedrock checks on what the LLM said."
            checks={[
              <>
                PII leakage <em>(emails, phone, addresses)</em>
              </>,
              <>Toxicity, harassment, slurs</>,
              <>
                Off-topic drift <em>(non-boutique content)</em>
              </>,
              <>Prompt-injection echoes</>,
            ]}
            runs={[
              <>
                AWS Bedrock guardrail <span className="gt-mono">v2</span>
              </>,
              <>Synchronous, ~40ms p50</>,
              <>Block on any flagged category</>,
              <>
                Logs go to <span className="gt-mono">cloudtrail</span>
              </>,
            ]}
          />
          <RuleDetailCard
            kind="approvals"
            number="II"
            name="Approvals."
            tagline="A human on state-changing actions."
            checksLabel="What it gates"
            checks={[
              <>
                <span className="gt-mono">place_order</span> · always
              </>,
              <>
                <span className="gt-mono">restock</span> · always
              </>,
              <>
                <span className="gt-mono">cancel_order</span> · always
              </>,
              <>Reads · auto-passed</>,
            ]}
            runs={[
              <>
                Item enters <span className="gt-mono">approvals</span> table
              </>,
              <>Boutique chat surfaces a confirm card</>,
              <>User taps confirm or deny</>,
              <>
                Reply ships <em>only after clearance</em>
              </>,
            ]}
          />
          <RuleDetailCard
            kind="grounding"
            number="III"
            name="Grounding."
            tagline="Facts checked against the source of truth."
            checksLabel="What it verifies"
            checks={[
              <>Prices in reply match Aurora catalog</>,
              <>Stock claims match warehouse</>,
              <>SKUs exist · no hallucinations</>,
              <>Policy quotes match policy doc</>,
            ]}
            runs={[
              <>Extract claims via small LLM call</>,
              <>Lookup against Aurora · ~28ms</>,
              <>Block on any mismatch</>,
              <>
                Mismatches feed eval <em>truth corner</em>
              </>,
            ]}
          />
        </div>
      </SectionFrame>

      {/* ---- Approvals queue spotlight ---- */}
      <div className="gt-queue-wrap">
        <SectionFrame
          eyebrow="The approvals queue"
          title={
            <>
              A human, <em>still in the loop.</em>
            </>
          }
          description="The approvals queue is the lane that's worth its own look. Reads pass through silently; writes wait for a human signal. Items live until they're cleared, denied, or expire."
        >
        <div className="gt-queue-frame">
          <div className="gt-queue-head">
            <div>
              <div className="gt-queue-eyebrow">
                <span className="gt-pulse-amber" aria-hidden /> Approvals · live
              </div>
              <div className="gt-queue-title">
                Items <em>awaiting confirmation.</em>
              </div>
            </div>
            <div className="gt-queue-meta">
              queue depth · 1 active · 4 cleared today
            </div>
          </div>
          <div className="gt-queue-rows">
            <div className="gt-q-row gt-q-row-head">
              <span>Stamp</span>
              <span>Tool</span>
              <span>Args</span>
              <span>Age</span>
              <span className="gt-q-status-col">Status</span>
            </div>
            {QUEUE_ITEMS.map((item, i) => (
              <div className="gt-q-row" key={`q-${i}`}>
                <span className="gt-q-stamp">{item.stamp}</span>
                <span className="gt-q-tool">{item.tool}</span>
                <span className="gt-q-args">{item.args}</span>
                <span
                  className={`gt-q-age${item.ageUrgent ? ' gt-q-age-urgent' : ''}`}
                >
                  {item.age}
                </span>
                <span className={`gt-q-status gt-q-status-${item.status}`}>
                  {item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
        </SectionFrame>
      </div>

      {/* ---- Cheat sheet ---- */}
      <CheatSheet
        eyebrow="When in doubt"
        title={
          <>
            Three rules <em>about gating.</em>
          </>
        }
        cells={[
          {
            key: 'PARALLEL',
            name: "Lanes don\u2019t wait on each other.",
            question: <em>"Why all at once?"</em>,
            list: [
              <>Three independent contracts, three independent runs</>,
              <>Wall-clock cost = max, not sum</>,
              <>Sequential gating is a smell · adds latency without safety</>,
              <>
                <em>
                  If one lane needs another's output, you've muddled them
                </em>
              </>,
            ],
          },
          {
            key: 'FAIL CLOSED',
            name: 'Block on uncertainty.',
            question: <em>"What if the check times out?"</em>,
            list: [
              <>Timeout → block, not pass</>,
              <>Unreachable lane → block, not skip</>,
              <>Partial result → block, then alert</>,
              <>
                <em>Default deny is the only safe default</em>
              </>,
            ],
          },
          {
            key: 'VISIBLE',
            name: 'Blocks must be explained.',
            question: <em>"What does the user see?"</em>,
            list: [
              <>Guardrail block → quiet retry, generic message</>,
              <>Approvals queued → confirm card in chat</>,
              <>Grounding block → re-fetch and rewrite once</>,
              <>
                <em>Silent blocks erode trust faster than slow ones</em>
              </>,
            ],
          },
        ]}
      />

      {/* ---- Live audit strip ---- */}
      {/* Live: the Approvals lane now surfaces Cedar policy decisions
          captured by the Strands BeforeToolCallEvent hook. Every tool
          the backend decides to allow or deny for this session appears
          here within ~3s. The stub grid below keeps the illustrative
          guardrails / grounding rows while those lanes are still
          unwired — they'll swap for live counterparts in Commits 11
          and a future grounding instrumentation pass. */}
      <LiveStrip
        eyebrow="Live · audit log"
        title={
          <>
            The boundary, <em>turn by turn.</em>
          </>
        }
        meta={
          <>
            {liveGuardrails.length + liveDecisions.length > 0
              ? `${liveGuardrails.length} guardrail · ${liveDecisions.length} policy · ${livePassCount + liveGuardrails.filter(g => g.allowed).length} pass · ${liveDenyCount + liveGuardrails.filter(g => !g.allowed).length} block`
              : 'awaiting first turn this session'}
          </>
        }
        stubCaption={
          liveGuardrails.length + liveDecisions.length > 0
            ? 'Guardrails + Approvals rows are live from backend events. Grounding rows still illustrative until the per-turn claim-verification pass ships.'
            : 'No live turns yet this session. All three lanes are illustrative.'
        }
      >
        <div className="gt-audit-rows">
          <div className="gt-audit-row gt-audit-row-head">
            <span>Stamp</span>
            <span>Lane</span>
            <span>Verdict</span>
            <span>Detail</span>
            <span className="gt-audit-ms-col">ms</span>
          </div>
          {liveGuardrails.map((g, i) => {
            const isBlock = !g.allowed
            const firstViolation = g.violations?.[0]
            const detail = isBlock
              ? `${firstViolation?.type ?? 'blocked'} · ${firstViolation?.confidence ?? ''}`.trim().replace(/\s+·\s*$/, '')
              : g.mode === 'pass-through'
                ? 'pass-through · no guardrail configured'
                : `no flags · ${g.source.toLowerCase()}`
            return (
              <div
                className="gt-audit-row"
                key={`gr-${g.timestamp_ms}-${i}`}
                data-testid="grounding-live-guardrail-row"
              >
                <span className="gt-audit-stamp">{formatStamp(g.timestamp_ms)}</span>
                <span className="gt-audit-lane gt-audit-lane-guardrails">
                  Guardrails
                </span>
                <span
                  className={`gt-audit-verdict gt-audit-verdict-${isBlock ? 'block' : 'pass'}`}
                >
                  {isBlock ? 'Block' : 'Pass'}
                </span>
                <span className="gt-audit-detail">{detail}</span>
                <span className="gt-audit-ms">
                  {typeof g.latency_ms === 'number' ? `${g.latency_ms}ms` : 'live'}
                </span>
              </div>
            )
          })}
          {liveDecisions.map((dec, i) => {
            const isDeny = dec.decision === 'DENY'
            const reason = isDeny
              ? (dec.violations?.[0]?.reason ?? 'policy denied')
              : `${dec.matching_policies.length} policies evaluated`
            return (
              <div className="gt-audit-row" key={`live-${dec.tool_use_id ?? i}`} data-testid="grounding-live-policy-row">
                <span className="gt-audit-stamp">{formatStamp(dec.timestamp_ms)}</span>
                <span className={`gt-audit-lane gt-audit-lane-approvals`}>
                  Approvals
                </span>
                <span
                  className={`gt-audit-verdict gt-audit-verdict-${isDeny ? 'block' : 'pass'}`}
                >
                  {isDeny ? 'Block' : 'Pass'}
                </span>
                <span className="gt-audit-detail">
                  {dec.tool_name} · <em>{reason}</em>
                </span>
                <span className="gt-audit-ms">live</span>
              </div>
            )
          })}
          {AUDIT_ROWS.map((row, i) => (
            <div className="gt-audit-row" key={`audit-${i}`}>
              <span className="gt-audit-stamp">{row.stamp}</span>
              <span className={`gt-audit-lane gt-audit-lane-${row.lane}`}>
                {row.laneLabel}
              </span>
              <span
                className={`gt-audit-verdict gt-audit-verdict-${row.verdict}`}
              >
                {row.verdictLabel}
              </span>
              <span className="gt-audit-detail">{row.detail}</span>
              <span className="gt-audit-ms">{row.ms}</span>
            </div>
          ))}
        </div>
      </LiveStrip>
    </DetailPageShell>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LaneCard({ lane }: { lane: Lane }) {
  return (
    <article className={`gt-lane gt-lane-${lane.status}`}>
      <header className="gt-lane-head">
        <span className="gt-lane-num">LANE · {lane.number}</span>
        <span className="gt-lane-status">{lane.statusLabel}</span>
      </header>
      <h3 className="gt-lane-name">
        <em>{lane.name}</em>
      </h3>
      <p className="gt-lane-tagline">{lane.tagline}</p>
      <ul className="gt-lane-checks">
        {lane.checks.map((check, i) => (
          <li className={`gt-lane-check gt-lane-check-${check.mark}`} key={i}>
            <span className="gt-lane-mark">
              {check.mark === 'ok' ? '✓' : check.mark === 'queued' ? '●' : '✕'}
            </span>
            <span>
              {check.text}
              {check.em && (
                <>
                  {' '}
                  <em>{check.em}</em>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
      <footer className="gt-lane-foot">
        <span>
          {lane.footLeft.num && (
            <>
              {lane.footLeft.label === 'ms' ? '~' : ''}
              <span className="gt-lane-foot-num">{lane.footLeft.num}</span>
              {lane.footLeft.label === 'ms' ? 'ms' : ` ${lane.footLeft.label}`}
            </>
          )}
          {!lane.footLeft.num && lane.footLeft.label}
        </span>
        <span>{lane.footRight}</span>
      </footer>
    </article>
  )
}

function RuleDetailCard({
  kind,
  number,
  name,
  tagline,
  checksLabel = 'What it checks',
  checks,
  runs,
}: {
  kind: LaneKind
  number: string
  name: string
  tagline: string
  checksLabel?: string
  checks: React.ReactNode[]
  runs: React.ReactNode[]
}) {
  return (
    <article className="gt-rd-card">
      <header className={`gt-rd-head gt-rd-head-${kind}`}>
        <span className="gt-rd-key">LANE · {number}</span>
        <h3 className="gt-rd-name">
          <em>{name}</em>
        </h3>
        <p className="gt-rd-tagline">{tagline}</p>
      </header>
      <div className="gt-rd-body">
        <div className="gt-rd-section">
          <div className="gt-rd-section-label">{checksLabel}</div>
          <ul className="gt-rd-list">
            {checks.map((item, i) => (
              <li key={`check-${i}`}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="gt-rd-section">
          <div className="gt-rd-section-label">How it runs</div>
          <ul className="gt-rd-list">
            {runs.map((item, i) => (
              <li key={`run-${i}`}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  )
}
