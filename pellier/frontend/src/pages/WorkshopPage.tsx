/**
 * WorkshopPage — the `/workshop` route (a.k.a. "The Atelier").
 *
 * Claude Desktop / artifact-pattern layout. Three zones:
 *   LEFT   — WorkshopChat (primary input surface, default ~40%).
 *   CENTER — Telemetry | Architecture | Performance tabs (default ~60%).
 *   RIGHT  — Detail panel slot (hidden by default, slides in when an
 *            architecture card opens a dashboard; compresses the center
 *            zone rather than replacing it so the trace narrative stays
 *            visible during live demos).
 *
 * Full viewport width, laptop-optimized for 1280+ screens. Three
 * responsive bands:
 *   ≥ 1280px  three-zone resizable split (react-resizable-panels).
 *   1024-1280 detail panel overlays the telemetry half when open.
 *   < 1024    single-column vertical stack, detail pushes below.
 *
 * Teaching anchor: "Use AgentCore for solved primitives. Use Aurora
 * for domain state you own." Each architecture card carries a
 * provenance pill (Managed / Owned / Both).
 *
 * Tab behavior:
 *   - Tabs render in order Telemetry → Architecture → Performance.
 *   - Default active tab is Architecture so first-time visitors get
 *     the orientation before they ask a question.
 *   - Once the first turn produces events, we flip to Telemetry one
 *     time (the "did it work?" moment).
 *   - The user's last explicit choice is persisted in localStorage so
 *     subsequent reloads open to where they last were.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels'
import {
  ArrowRight,
} from 'lucide-react'
import Footer from '../components/Footer'
import Header from '../components/Header'
import { AuthGate } from '../App'
import PatternsTab from '../components/PatternsTab'
import WorkshopChat from '../components/WorkshopChat'
import WorkshopTelemetry from '../components/WorkshopTelemetry'
import {
  HnswBenchmarkSection,
  QuantizationSection,
  IterativeScanSection,
} from '../components/PgvectorBenchSections'
import SkillsPanel from '../components/SkillsPanel'
import MemoryArchPage from '../components/atelier-arch/MemoryArchPage'
import McpArchPage from '../components/atelier-arch/McpArchPage'
import ToolRegistryArchPage from '../components/atelier-arch/ToolRegistryArchPage'
import RuntimeArchPage from '../components/atelier-arch/RuntimeArchPage'
import StateManagementArchPage from '../components/atelier-arch/StateManagementArchPage'
import EvaluationsArchPage from '../components/atelier-arch/EvaluationsArchPage'
import GroundingArchPage from '../components/atelier-arch/GroundingArchPage'
import type { SkillRouting } from '../hooks/useAgentChat'
import { useUI } from '../contexts/UIContext'
import AtelierHero from '../components/AtelierHero'
import AtelierSpotlight from '../components/AtelierSpotlight'
import AtmosphereStrip from '../components/AtmosphereStrip'
import MetricsRow from '../components/MetricsRow'
import { useScrollAndFlash } from '../hooks/useScrollAndFlash'
import type { WorkshopEvent, WorkshopPanelEvent } from '../services/workshop'

const CREAM = '#fbf4e8'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM_WARM = '#f5e8d3'
const ACCENT = '#c44536'

type Tab = 'telemetry' | 'architecture' | 'patterns' | 'performance'

type Provenance = 'MANAGED' | 'OWNED' | 'BOTH'

type DetailPanelKey =
  | 'skills'
  // Atelier architecture detail pages (Phase 2+)
  | 'arch-memory'
  | 'arch-mcp'
  | 'arch-state-management'
  | 'arch-tool-registry'
  | 'arch-runtime'
  | 'arch-evaluations'
  | 'arch-grounding'
  | null

// URL param <-> DetailPanelKey mapping.
// The URL shape is ``/atelier/architecture/<section>`` so we use
// kebab-case segments that read well in address bars. The old
// in-workbench panels (memory / gateway / runtime dashboards) are
// gone — the arch-* detail pages replaced them.
const SECTION_TO_PANEL: Record<string, Exclude<DetailPanelKey, null>> = {
  skills: 'skills',
  memory: 'arch-memory',
  mcp: 'arch-mcp',
  'state-management': 'arch-state-management',
  'tool-registry': 'arch-tool-registry',
  runtime: 'arch-runtime',
  evaluations: 'arch-evaluations',
  grounding: 'arch-grounding',
}
const PANEL_TO_SECTION: Partial<Record<Exclude<DetailPanelKey, null>, string>> = {
  skills: 'skills',
  'arch-memory': 'memory',
  'arch-mcp': 'mcp',
  'arch-state-management': 'state-management',
  'arch-tool-registry': 'tool-registry',
  'arch-runtime': 'runtime',
  'arch-evaluations': 'evaluations',
  'arch-grounding': 'grounding',
}

// Provenance → (pill colors, icon, icon tint). The icon + its tint
// double-encode the provenance so a card reads correctly even if
// the pill falls out of the user's scan path.
const PROV_META: Record<
  Provenance,
  {
    pillBg: string
    pillFg: string
    label: string
  }
> = {
  MANAGED:  { pillBg: '#E6F1FB', pillFg: '#0C447C', label: 'Managed' },
  OWNED:    { pillBg: '#EAF3DE', pillFg: '#27500A', label: 'Owned' },
  BOTH:     { pillBg: '#EEEDFE', pillFg: '#3C3489', label: 'Both' },
}

type CardCTA =
  | { kind: 'action'; label: string; open: Exclude<DetailPanelKey, null> }
  | { kind: 'in-progress' }
  | { kind: 'none' }

interface ArchCard {
  id: string
  title: string
  provenance: Provenance
  description: string
  cta: CardCTA
  /** Featured cards span the full grid width. */
  featured: boolean
  /** Roman chapter numeral, e.g. "i.", "ii." */
  chapter: string
  /** Signature code line(s) shown in the cream-warm code block. */
  signature: string[]
}

// Card order follows the agent's actual flow so an L400 reader
// infers the story: context → capabilities → protocol → data →
// compute → safety → measurement.
const ARCH_CARDS: ArchCard[] = [
  {
    id: 'memory',
    title: 'Memory',
    provenance: 'BOTH',
    description:
      'AgentCore Memory holds short-term conversation state; Aurora pgvector holds long-term semantic + procedural recall. Two tiers, one session id — the agent reads from whichever gives the right context for the turn.',
    cta: { kind: 'action', label: 'Open memory architecture', open: 'arch-memory' },
    featured: true,
    chapter: 'i.',
    signature: [
      'stm = agentcore.memory.get(session_id)',
      'ltm = aurora.find_similar(emb, customer_id)',
    ],
  },
  {
    id: 'skills',
    title: 'Skills',
    provenance: 'OWNED',
    description:
      "Folders of domain expertise loaded into the agent's context only when the conversation needs them. Skills don't pick products and they don't fetch data — they shape how the agent thinks and writes about a topic. Pellier ships two: style-advisor and gift-concierge.",
    cta: { kind: 'action', label: 'Open skills architecture', open: 'skills' },
    featured: true,
    chapter: 'ii.',
    signature: [
      'router.route(user_message) -> [skill]',
      'inject_skills(base_prompt, loaded_skills)',
    ],
  },
  {
    id: 'mcp',
    title: 'MCP',
    provenance: 'MANAGED',
    description:
      "Model Context Protocol is an open standard; AgentCore Gateway is AWS's managed MCP server. This workshop uses Gateway as the MCP primitive — you could run your own MCP server, but Gateway handles tool publishing, auth, and observability for you.",
    cta: { kind: 'action', label: 'Open MCP architecture', open: 'arch-mcp' },
    featured: false,
    chapter: 'iii.',
    signature: ['gateway.list_tools() -> MCPToolset'],
  },
  {
    id: 'state',
    title: 'State Management',
    provenance: 'OWNED',
    description:
      'Session state lives in Postgres — orders, customers, approvals, tool audit. Aurora is the source of truth for domain facts the agents grant themselves access to; AgentCore never tries to own this side of the system.',
    cta: { kind: 'action', label: 'Open state architecture', open: 'arch-state-management' },
    featured: false,
    chapter: 'iv.',
    signature: ['SELECT * FROM orders WHERE customer_id = $1 ...'],
  },
  {
    id: 'tool-registry',
    title: 'Tool Registry · Gateway',
    provenance: 'BOTH',
    description:
      "AgentCore Gateway publishes tools via MCP to any runtime; the teaching deconstruction shows the same discovery primitive implemented over Aurora pgvector. Both columns rank the same 9 tools — you see what Gateway abstracts for you.",
    cta: { kind: 'action', label: 'Open tool registry', open: 'arch-tool-registry' },
    featured: true,
    chapter: 'v.',
    signature: [
      'SELECT name, 1 - (description_emb <=> $1) AS score',
      'FROM tools ORDER BY description_emb <=> $1 LIMIT 4;',
    ],
  },
  {
    id: 'runtime',
    title: 'Runtime',
    provenance: 'MANAGED',
    description:
      "AgentCore Runtime runs the orchestrator inside a managed microVM — scale, cold-start, and VPC wiring are AWS's problem. Flip USE_AGENTCORE_RUNTIME on to promote the same code from local FastAPI to the hosted runtime without touching the orchestrator.",
    cta: { kind: 'action', label: 'Open runtime architecture', open: 'arch-runtime' },
    featured: false,
    chapter: 'vi.',
    signature: ['runtime.invoke(orchestrator, payload)'],
  },
  {
    id: 'evaluations',
    title: 'Evaluations',
    provenance: 'MANAGED',
    description:
      "AgentCore Evaluations scores every turn using LLM-as-a-Judge over the OpenTelemetry traces Strands already emits. Built-in evaluators measure helpfulness, tool accuracy, and consistency; custom evaluators let you add domain-specific checks. Online mode scores live traffic; on-demand mode runs a dataset batch for regression.",
    cta: { kind: 'action', label: 'Open evaluations architecture', open: 'arch-evaluations' },
    featured: false,
    chapter: 'vii.',
    signature: ['evaluations.run(traces) -> {helpfulness, tool_accuracy, consistency}'],
  },
  {
    id: 'grounding',
    title: 'Grounding · Approvals · Guardrails',
    provenance: 'BOTH',
    description:
      'Bedrock guardrails on the LLM; Aurora-backed approvals queue for sensitive tool calls (place_order, restock). One card because all three fire on the same turn boundary — the answer leaves only if it survives every check.',
    cta: { kind: 'action', label: 'Open grounding architecture', open: 'arch-grounding' },
    featured: true,
    chapter: 'viii.',
    signature: ['guardrails.check(claims) ; approvals.queue(tool_call)'],
  },
]

function ProvenancePill({ kind }: { kind: Provenance }) {
  const m = PROV_META[kind]
  return (
    <span
      className="text-[10px] font-medium uppercase whitespace-nowrap"
      style={{
        color: m.pillFg,
        background: m.pillBg,
        padding: '4px 10px',
        borderRadius: 4,
        letterSpacing: '0.16em',
        fontWeight: 500,
      }}
    >
      {m.label}
    </span>
  )
}

/**
 * Architecture card — magazine-card treatment per the pre-Week-3
 * redesign. Icon tile top-left, provenance pill top-right, title in
 * Instrument Serif, body at 4-line clamp, fine rule before the CTA.
 *
 * CTA patterns:
 *   action       — solid link with arrow, opens the detail panel.
 *   in-progress  — disabled pill labeled "In progress" (operator
 *                  register for deferred surfaces that will ship).
 *   none         — no CTA at all; card stands on its body copy.
 *
 * When the card's detail panel is open, a 3px terracotta left border
 * + quiet cream-warm fill mark it active; the CTA label flips to
 * "Viewing · click to close".
 */
function ArchitectureCard({
  card,
  onOpen,
  active,
}: {
  card: ArchCard
  onOpen: (key: Exclude<DetailPanelKey, null>) => void
  active: boolean
}) {
  const isActionCard = card.cta.kind === 'action'
  const ctaLabel = card.cta.kind === 'action' ? card.cta.label : ''
  const ctaOpen = card.cta.kind === 'action' ? card.cta.open : null

  return (
    <article
      data-testid={`arch-card-${card.id}`}
      data-active={active ? 'true' : 'false'}
      className="relative rounded-xl flex flex-col transition-all duration-200 ease-out"
      style={{
        gridColumn: card.featured ? '1 / -1' : undefined,
        background: active ? CREAM_WARM : 'white',
        border: `1px solid ${active ? `${ACCENT}60` : 'rgba(45, 24, 16, 0.12)'}`,
        borderLeft: active ? `3px solid ${ACCENT}` : `1px solid rgba(45, 24, 16, 0.12)`,
        padding: '22px 24px',
      }}
    >
      {/* (a) Header — chapter numeral + title + provenance pill, all one line */}
      <div className="flex items-baseline justify-between gap-3 mb-[10px]">
        <div className="flex items-baseline gap-2.5">
          <span
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontStyle: 'italic',
              fontSize: 18,
              color: INK_QUIET,
            }}
          >
            {card.chapter}
          </span>
          <h3
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontSize: 22,
              fontWeight: 400,
              margin: 0,
              color: INK,
              letterSpacing: '-0.01em',
            }}
          >
            {card.title}
          </h3>
        </div>
        <ProvenancePill kind={card.provenance} />
      </div>

      {/* (c) Body */}
      <p
        className="text-[14px] leading-[1.7]"
        style={{
          color: INK_SOFT,
          margin: '0 0 16px',
          maxWidth: card.featured ? 580 : undefined,
        }}
      >
        {card.description}
      </p>

      {/* (d) Signature code block */}
      <div
        className="font-mono text-[11px] leading-[1.7]"
        style={{
          background: CREAM_WARM,
          borderRadius: 6,
          padding: '11px 14px',
          color: INK,
          marginBottom: card.cta.kind !== 'none' ? 16 : 0,
        }}
      >
        {card.signature.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>

      {/* (e) Action */}
      {isActionCard && card.cta.kind === 'action' && (
        <button
          type="button"
          onClick={() => ctaOpen && onOpen(ctaOpen)}
          data-testid={`arch-card-open-${card.id}`}
          className="self-start inline-flex items-center gap-1.5 text-[13px] font-medium transition-opacity hover:opacity-75"
          style={{ color: ACCENT }}
        >
          {active ? 'Viewing · click to close' : ctaLabel}
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
      {card.cta.kind === 'in-progress' && (
        <span
          data-testid={`arch-card-inprogress-${card.id}`}
          className="self-start font-mono text-[10px] uppercase tracking-[1.3px] px-2 py-0.5 rounded"
          style={{
            color: INK_QUIET,
            border: `1px solid ${INK_QUIET}40`,
            background: 'rgba(0,0,0,0.02)',
          }}
        >
          In progress
        </span>
      )}
    </article>
  )
}

/**
 * matchMedia hook. Returns true when the viewport matches ``query``.
 * Re-evaluates on resize / orientation change.
 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [query])

  return matches
}

// Tab order in the UI (Telemetry leads because that's where attendees
// actually test a query). Default active tab is Architecture so the
// first-time visitor gets orientation before dissection — see
// ``useTabState`` below.
const TAB_ORDER: Tab[] = ['telemetry', 'architecture', 'patterns', 'performance']

const TAB_STORAGE_KEY = 'pellier-atelier-tab'

/**
 * Tab state with first-events auto-switch + localStorage persistence.
 *
 * - On first mount: read localStorage; if unset, default to
 *   ``'architecture'``.
 * - When the first panel event arrives on a first-time visit (no
 *   stored preference yet), auto-switch to Telemetry one time and
 *   save that choice. Subsequent events don't re-switch.
 * - Every explicit user tab click is persisted.
 *
 * The "one-time auto-switch" behavior matters for the live demo: we
 * want the first query to move the speaker's focus to the trace
 * without overriding the attendee who clicked back to Architecture
 * mid-turn.
 */
/**
 * usePerformanceRuntime — live aggregates for the Performance tab.
 *
 * Pulls /api/performance/runtime every 5s so the bar chart + metric
 * strip + cold-start histogram reflect the actual turns this session
 * has observed. When the buffer is empty (no turns yet) the hook
 * returns ``null`` and the render path falls back to the hardcoded
 * illustrative numbers — the UI should never fake measurements it
 * doesn't have.
 */
interface PerformanceAggregates {
  turn_count: number
  empty: boolean
  layers_p50?: Record<string, number>
  layers_p95?: Record<string, number>
  total_p50?: number
  total_p95?: number
  ttft_p50?: number
  ttft_p95?: number
  histogram?: number[]
  tools_p50?: Record<string, number>
}

function usePerformanceRuntime(enabled: boolean): PerformanceAggregates | null {
  const [agg, setAgg] = useState<PerformanceAggregates | null>(null)
  useEffect(() => {
    if (!enabled) return
    let alive = true
    const pull = () => {
      fetch('/api/performance/runtime')
        .then(r => r.json())
        .then(d => {
          if (!alive) return
          if (d && typeof d === 'object') setAgg(d as PerformanceAggregates)
        })
        .catch(() => {
          /* quiet */
        })
    }
    pull()
    const id = setInterval(pull, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [enabled])
  return agg
}

function useTabState(panelCount: number): [Tab, (t: Tab) => void] {
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    if (typeof window === 'undefined') return 'telemetry'
    const stored = window.localStorage.getItem(TAB_STORAGE_KEY) as Tab | null
    // Telemetry is the Atelier's front door. The 13-panel empty state
    // teaches the pipeline on page load; Architecture remains a click
    // away. Only honour a stored value if it's an explicit user
    // choice that landed on telemetry or performance — architecture
    // as a stored default was an older behaviour.
    return stored && TAB_ORDER.includes(stored) ? stored : 'telemetry'
  })
  const autoSwitched = useRef(false)

  const setActiveTabPersisted = (t: Tab) => {
    setActiveTab(t)
    try {
      window.localStorage.setItem(TAB_STORAGE_KEY, t)
    } catch {
      // private mode / storage disabled — state-only tab is fine.
    }
    autoSwitched.current = true // explicit user choice ends auto-switching
  }

  useEffect(() => {
    if (autoSwitched.current) return
    if (panelCount === 0) return
    if (typeof window !== 'undefined' && window.localStorage.getItem(TAB_STORAGE_KEY)) {
      autoSwitched.current = true
      return
    }
    setActiveTab('telemetry')
    autoSwitched.current = true
  }, [panelCount])

  return [activeTab, setActiveTabPersisted]
}

function WorkshopContent() {
  const navigate = useNavigate()
  const { section } = useParams<{ section?: string }>()
  const [events, setEvents] = useState<WorkshopEvent[]>([])
  const [detailPanel, setDetailPanel] = useState<DetailPanelKey>(null)

  // Tell UIProvider that ⌘K should open the concierge modal (not the
  // drawer) while on atelier routes.
  const { setChatSurface } = useUI()
  useEffect(() => {
    setChatSurface('concierge')
  }, [setChatSurface])

  // Sync URL :section param → detailPanel on mount and on URL changes.
  // Tabs stay in component state (Architecture/Telemetry/Performance);
  // only detail-page opens land in the URL as /atelier/architecture/<name>.
  useEffect(() => {
    if (!section) {
      // Nav'd to /atelier with no section — close any open detail panel
      // that was opened via a previous deep link.
      setDetailPanel((prev) => (prev && PANEL_TO_SECTION[prev] ? null : prev))
      return
    }
    const mapped = SECTION_TO_PANEL[section]
    if (mapped) setDetailPanel(mapped)
  }, [section])
  // Most recent skill routing decision — persisted by useAgentChat in
  // localStorage so the Atelier Skills panel can read the decision
  // captured by the storefront chat on another route. Polls every
  // 2 seconds while the panel is open; cheap and avoids cross-route
  // context plumbing.
  const [skillRouting, setSkillRouting] = useState<SkillRouting | null>(() => {
    try {
      const stored = localStorage.getItem('pellier-skill-routing-latest')
      return stored ? (JSON.parse(stored) as SkillRouting) : null
    } catch {
      return null
    }
  })

  // Poll localStorage for the latest skill routing decision. Runs
  // unconditionally (not gated on the Skills detail panel being open)
  // so the MetricsRow + AtmosphereStrip can show "Skills · this turn"
  // from the moment the storefront or atelier chat lands a routing
  // event. 2s interval is cheap and avoids cross-route context.
  useEffect(() => {
    const tick = () => {
      try {
        const stored = localStorage.getItem('pellier-skill-routing-latest')
        if (!stored) return
        const parsed = JSON.parse(stored) as SkillRouting
        setSkillRouting((prev) => {
          if (
            prev &&
            prev.user_message === parsed.user_message &&
            prev.elapsed_ms === parsed.elapsed_ms
          ) {
            return prev
          }
          return parsed
        })
      } catch {
        // ignore
      }
    }
    tick()
    const t = setInterval(tick, 2000)
    return () => clearInterval(t)
  }, [])
  // Lifted from WorkshopChat so the right-rail band can render the
  // live session id + customer label inline alongside its
  // "ATELIER / TELEMETRY" kicker.
  const [sessionInfo, setSessionInfo] = useState<{
    sessionId: string | null
    customerLabel: string
  }>({ sessionId: null, customerLabel: 'Anonymous' })

  // Cross-panel citation scroll + 800ms terracotta pulse. Chat calls
  // ``scrollToTrace(ref)`` when a citation pill / "view trace" /
  // "Open in trace" link is clicked; the hook resolves the ref
  // against the right-rail panel cards by testid.
  const { containerRef: traceContainerRef, scrollToTrace } = useScrollAndFlash()

  const handleOpenTrace = (traceRef: string) => {
    // Ensure the Telemetry tab is showing before attempting to scroll —
    // a citation click while on Architecture should swap tabs first.
    if (activeTab !== 'telemetry') setActiveTab('telemetry')
    // Defer the scroll so the tab swap has a chance to mount the
    // panel cards before we query for them.
    requestAnimationFrame(() => scrollToTrace(traceRef))
  }

  // Three responsive bands: ≥ 1280 three-zone resizable, 1024-1280
  // detail overlays, < 1024 vertical stack.
  const isLaptop = useMediaQuery('(min-width: 1280px)')
  const isTablet = useMediaQuery('(min-width: 1024px) and (max-width: 1279.98px)')

  const panelCount = events.filter((e) => e.type === 'panel').length
  const [activeTab, setActiveTab] = useTabState(panelCount)

  // Live performance aggregates — only pulled when the Performance
  // tab is visible so we don't burn a fetch every 5s on unrelated tabs.
  const perfAggregates = usePerformanceRuntime(activeTab === 'performance')
  const hasLivePerf = !!perfAggregates && !perfAggregates.empty

  // Four real metrics feeding the MetricsRow + AtmosphereStrip. All
  // derived from the current turn's events — no stubs, no per-session
  // counters that reset on reload.
  const metrics = useMemo(() => {
    const panels = events.filter(
      (e): e is WorkshopPanelEvent => e.type === 'panel',
    )
    const toolsUsed = panels.filter((p) => p.tag_class === 'cyan').length
    const elapsedMs = events.length
      ? events[events.length - 1].ts_ms - events[0].ts_ms
      : null
    // Median of the current turn's panel durations. AtmosphereStrip
    // renders this; the MetricsRow uses the turn-elapsed instead.
    let medianMs: number | null = null
    if (panels.length > 0) {
      const sorted = [...panels].map((p) => p.duration_ms).sort((a, b) => a - b)
      const mid = Math.floor(sorted.length / 2)
      medianMs =
        sorted.length % 2 === 0
          ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
          : sorted[mid]
    }
    // CONFIDENCE · last reply reads the ``result`` row of the most
    // recent MEMORY · CONFIDENCE panel. The panel's emitter writes
    // the percent as the "result" row's contribution cell (see
    // services/workshop_panels.compute_confidence); we parse leading
    // digits so "94 (clamped to [30, 98])" still yields 94.
    let confidencePercent: number | null = null
    for (let i = panels.length - 1; i >= 0; i--) {
      if (panels[i].tag === 'MEMORY · CONFIDENCE') {
        const resultRow = panels[i].rows.find(
          (r) => r[0]?.toLowerCase() === 'result',
        )
        if (resultRow && resultRow[1]) {
          const match = resultRow[1].match(/\d+/)
          if (match) confidencePercent = parseInt(match[0], 10)
        }
        break
      }
    }
    // Skills loaded this turn — sourced from the latest routing decision
    // that ``useAgentChat`` writes to localStorage and WorkshopPage
    // polls above. Falls back to 0 until the first turn lands.
    const skillCount = skillRouting?.loaded_skills.length ?? 0
    return { panels, toolsUsed, elapsedMs, medianMs, confidencePercent, skillCount }
  }, [events, skillRouting])

  const detailOpen = detailPanel !== null
  // isBenchModal removed — pgvector benchmarks are now inline in the Performance tab

  const closeDetail = () => {
    // If the panel was opened via deep link, nav back to /atelier so
    // the URL reflects the closed state. Browser back/forward stays
    // clean. If there's no section param (panel was opened in-page),
    // only local state changes.
    setDetailPanel(null)
    if (section) navigate('/atelier')
  }
  const openDetail = (key: Exclude<DetailPanelKey, null>) => {
    setDetailPanel(key)
    const urlSection = PANEL_TO_SECTION[key]
    if (urlSection) navigate(`/atelier/architecture/${urlSection}`)
  }

  const renderDetail = () => {
    if (detailPanel === 'skills')
      return (
        <SkillsDetailWrapper onClose={closeDetail} routing={skillRouting} />
      )
    // --- Atelier architecture detail pages (Phase 2+) ---
    if (detailPanel === 'arch-memory')
      return <ArchDetailWrapper title="Memory" onClose={closeDetail}><MemoryArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-mcp')
      return <ArchDetailWrapper title="MCP" onClose={closeDetail}><McpArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-tool-registry')
      return <ArchDetailWrapper title="Tool Registry" onClose={closeDetail}><ToolRegistryArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-runtime')
      return <ArchDetailWrapper title="Runtime" onClose={closeDetail}><RuntimeArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-state-management')
      return <ArchDetailWrapper title="State Management" onClose={closeDetail}><StateManagementArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-evaluations')
      return <ArchDetailWrapper title="Evaluations" onClose={closeDetail}><EvaluationsArchPage /></ArchDetailWrapper>
    if (detailPanel === 'arch-grounding')
      return <ArchDetailWrapper title="Grounding · Approvals · Guardrails" onClose={closeDetail}><GroundingArchPage /></ArchDetailWrapper>
    return null
  }

  const workArea = (
    <div
      className="flex flex-col h-full rounded-xl overflow-hidden min-w-0"
      style={{
        background: 'rgba(255,255,255,0.7)',
        border: `1px solid ${INK_QUIET}30`,
      }}
    >
      {/* Sticky section label — "ATELIER / TELEMETRY" kicker on the
          left, session id · customer · elapsed on the right. Mirrors
          the "ATELIER / CHAT" band on the left card — same height,
          padding, border, letter-spacing. */}
      <div
        data-testid="session-header"
        className="flex items-center gap-3 px-5 py-[14px] text-[10px] uppercase font-medium"
        style={{
          background: CREAM_WARM,
          borderBottom: `1px solid ${INK_QUIET}20`,
          color: INK_QUIET,
          letterSpacing: '0.16em',
        }}
      >
        <span>Atelier / Telemetry</span>
        <span className="flex-1 h-[1px]" style={{ background: `${INK_QUIET}30` }} />
        <span
          className="font-mono normal-case tracking-normal text-[11px]"
          style={{ color: INK_SOFT, letterSpacing: 0 }}
        >
          {sessionInfo.sessionId ?? '—'}
          <span style={{ color: INK_QUIET }}> · </span>
          {sessionInfo.customerLabel}
          <span style={{ color: INK_QUIET }}> · </span>
          {metrics.elapsedMs === null ? '—' : `${metrics.elapsedMs}ms`}
        </span>
      </div>

      <div
        role="tablist"
        className="flex gap-1.5 px-5 pt-3"
        style={{ borderBottom: '1px solid rgba(45, 24, 16, 0.12)' }}
      >
        {TAB_ORDER.map((t) => {
          const active = activeTab === t
          const showCount = t === 'telemetry' && panelCount > 0
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`workshop-tab-${t}`}
              onClick={() => setActiveTab(t)}
              className="px-[18px] py-[9px] text-[13px] font-medium transition-colors flex items-center gap-1.5"
              style={
                active
                  ? {
                      background: INK,
                      color: CREAM,
                      borderRadius: '8px 8px 0 0',
                    }
                  : { color: INK_SOFT, background: 'transparent' }
              }
            >
              <span className="capitalize">{t}</span>
              {showCount && (
                <span
                  className="font-mono text-[10px] px-[7px] rounded-full"
                  style={{
                    background: '#c44536',
                    color: 'white',
                    lineHeight: 1.6,
                  }}
                >
                  {panelCount}
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div
        ref={traceContainerRef}
        className="flex-1 overflow-y-auto min-h-0 px-5 py-5"
      >
        {activeTab === 'architecture' && (
          <div className="flex flex-col gap-5">
            {/* Tab hero — "SEVEN CONCEPTS / Architecture — what makes Pellier work." */}
            <div className="mb-2">
              <div
                className="text-[10px] font-medium uppercase mb-2"
                style={{ color: ACCENT, letterSpacing: '0.18em', fontWeight: 500 }}
              >
                Seven concepts
              </div>
              <div className="flex items-baseline gap-4">
                <h2
                  style={{
                    fontFamily: 'Fraunces, Georgia, serif',
                    fontSize: 32,
                    lineHeight: 1,
                    margin: 0,
                    color: INK,
                    fontWeight: 400,
                    letterSpacing: '-0.01em',
                  }}
                >
                  Architecture
                </h2>
                <span
                  style={{
                    fontFamily: 'Fraunces, Georgia, serif',
                    fontStyle: 'italic',
                    fontSize: 15,
                    color: INK_QUIET,
                  }}
                >
                  — Pellier, disassembled.
                </span>
              </div>
            </div>

            {/* Bento grid — featured cards span full width */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {ARCH_CARDS.map((c) => (
                <ArchitectureCard
                  key={c.id}
                  card={c}
                  onOpen={openDetail}
                  active={c.cta.kind === 'action' && c.cta.open === detailPanel}
                />
              ))}
            </div>

            {/* Legend strip */}
            <div
              className="flex items-center gap-[18px] flex-wrap text-[11px]"
              style={{
                background: 'rgba(245, 232, 211, 0.5)',
                borderRadius: 8,
                padding: '14px 16px',
                color: INK_SOFT,
              }}
            >
              <span
                className="text-[10px] uppercase"
                style={{ color: INK_QUIET, letterSpacing: '0.18em' }}
              >
                Legend
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ProvenancePill kind="MANAGED" />
                <span>AWS managed primitive.</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ProvenancePill kind="OWNED" />
                <span>Postgres is source of truth.</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ProvenancePill kind="BOTH" />
                <span>Managed primitive + your data.</span>
              </span>
            </div>
          </div>
        )}
        {activeTab === 'telemetry' && <WorkshopTelemetry events={events} />}
        {activeTab === 'patterns' && <PatternsTab />}
        {activeTab === 'performance' && (
          <div className="flex flex-col gap-5">
            {/* Hero */}
            <div className="mb-2">
              <div
                className="text-[10px] font-medium uppercase mb-2"
                style={{ color: ACCENT, letterSpacing: '0.18em', fontWeight: 500 }}
              >
                Operational truth
              </div>
              <div className="flex items-baseline gap-4">
                <h2
                  style={{
                    fontFamily: 'Fraunces, Georgia, serif',
                    fontSize: 32,
                    lineHeight: 1,
                    margin: 0,
                    color: INK,
                    fontWeight: 400,
                    letterSpacing: '-0.01em',
                  }}
                >
                  Performance
                </h2>
                <span
                  style={{
                    fontFamily: 'Fraunces, Georgia, serif',
                    fontStyle: 'italic',
                    fontSize: 15,
                    color: INK_QUIET,
                  }}
                >
                  — how the system behaves at scale.
                </span>
              </div>
            </div>

            {/* Metric strip — swaps to live p50/p95 when the buffer
                has observed at least one turn this session, otherwise
                shows the illustrative placeholders. */}
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg p-4" style={{ background: 'white', border: '1px solid rgba(45, 24, 16, 0.12)' }} data-testid="perf-metric-total">
                <div className="text-[10px] uppercase mb-1.5" style={{ color: INK_QUIET, letterSpacing: '0.16em' }}>
                  {hasLivePerf ? 'P50 Turn total' : 'P50 Cold-start'}
                </div>
                <div style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 24, lineHeight: 1, color: INK }}>
                  {hasLivePerf
                    ? (perfAggregates!.total_p50! >= 1000
                        ? <>{(perfAggregates!.total_p50! / 1000).toFixed(1)}<span className="text-[13px] ml-0.5" style={{ color: INK_QUIET }}>s</span></>
                        : <>{Math.round(perfAggregates!.total_p50!)}<span className="text-[13px] ml-0.5" style={{ color: INK_QUIET }}>ms</span></>)
                    : <>2.4<span className="text-[13px] ml-0.5" style={{ color: INK_QUIET }}>s</span></>}
                </div>
                <div className="text-[11px] mt-1.5" style={{ color: INK_SOFT }}>
                  {hasLivePerf
                    ? `${perfAggregates!.turn_count} turn${perfAggregates!.turn_count === 1 ? '' : 's'} · live`
                    : '20 samples · bimodal'}
                </div>
              </div>
              <div className="rounded-lg p-4" style={{ background: 'white', border: '1px solid rgba(45, 24, 16, 0.12)' }} data-testid="perf-metric-ttft">
                <div className="text-[10px] uppercase mb-1.5" style={{ color: INK_QUIET, letterSpacing: '0.16em' }}>
                  {hasLivePerf ? 'P50 Time-to-first-token' : 'P50 Warm-start'}
                </div>
                <div style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 24, lineHeight: 1, color: INK }}>
                  {hasLivePerf
                    ? <>{Math.round(perfAggregates!.ttft_p50!)}<span className="text-[13px] ml-0.5" style={{ color: INK_QUIET }}>ms</span></>
                    : <>52<span className="text-[13px] ml-0.5" style={{ color: INK_QUIET }}>ms</span></>}
                </div>
                <div className="text-[11px] mt-1.5" style={{ color: INK_SOFT }}>
                  {hasLivePerf
                    ? `95th: ${Math.round(perfAggregates!.ttft_p95!)}ms`
                    : '95th: 78ms'}
                </div>
              </div>
            </div>

            {/* i. Runtime — cold-start histogram */}
            <div className="rounded-xl" style={{ background: 'white', border: '1px solid rgba(45, 24, 16, 0.12)', padding: '22px 24px' }}>
              <div className="flex justify-between items-start mb-[14px]">
                <span style={{ fontFamily: 'Fraunces, Georgia, serif', fontStyle: 'italic', fontSize: 18, color: INK_QUIET }}>i.</span>
                <span className="text-[10px] font-medium uppercase px-[10px] py-1 rounded" style={{ background: '#FAEEDA', color: '#633806', letterSpacing: '0.16em' }}>Runtime</span>
              </div>
              <h3 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 22, fontWeight: 400, margin: '0 0 10px', color: INK, letterSpacing: '-0.01em' }}>
                Cold-start, in two states.
              </h3>
              <p className="text-[14px] leading-[1.7] mb-[18px]" style={{ color: INK_SOFT, maxWidth: 580 }}>
                Managed runtime cold-start is bimodal - fresh container ~2.4s, warm reuse ~52ms. Twenty samples, sixty-second cooldowns. The teaching moment: every managed primitive has this shape; pre-warm or accept it.
              </p>
              {/* Histogram — real bucket counts when the runtime
                  buffer has observed turns; illustrative stub bars
                  otherwise. We normalize live bucket counts to 0..100
                  for height so the shape is visible regardless of
                  sample volume. */}
              <div className="flex items-end gap-[3px] mb-[14px] pb-2" style={{ height: 80, borderBottom: '1px solid rgba(45, 24, 16, 0.08)' }}>
                {(() => {
                  const stubBars = [18,8,65,88,95,72,30,12,5,5,5,5,0,0,0,28,55,38,18,8]
                  let bars: number[]
                  if (hasLivePerf && Array.isArray(perfAggregates!.histogram) && perfAggregates!.histogram!.length > 0) {
                    const live = perfAggregates!.histogram!
                    const maxCount = Math.max(1, ...live)
                    bars = live.map((n) => Math.round((n / maxCount) * 95))
                  } else {
                    bars = stubBars
                  }
                  return bars.map((h, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-t-sm"
                      style={{
                        height: `${Math.max(0, h)}%`,
                        background: h > 10 ? ACCENT : 'rgba(45, 24, 16, 0.15)',
                      }}
                    />
                  ))
                })()}
              </div>
              <div className="flex justify-between font-mono text-[10px] mb-[14px]" style={{ color: INK_QUIET }}>
                <span>0ms</span><span>500ms</span><span>1.5s</span><span>2.5s</span><span>3.5s</span>
              </div>
              <div className="font-mono text-[11px] leading-[1.7] rounded-md" style={{ background: CREAM_WARM, color: INK, padding: '11px 14px' }}>
                <span style={{ color: ACCENT }}>python</span> scripts/bench_runtime_coldstart.py --samples 20
              </div>
            </div>

            {/* ii. Per Panel — latency bar chart */}
            <div className="rounded-xl" style={{ background: 'white', border: '1px solid rgba(45, 24, 16, 0.12)', padding: '22px 24px' }}>
              <div className="flex justify-between items-start mb-[14px]">
                <span style={{ fontFamily: 'Fraunces, Georgia, serif', fontStyle: 'italic', fontSize: 18, color: INK_QUIET }}>ii.</span>
                <span className="text-[10px] font-medium uppercase px-[10px] py-1 rounded" style={{ background: '#E6F1FB', color: '#0C447C', letterSpacing: '0.16em' }}>Per Panel</span>
              </div>
              <h3 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 22, fontWeight: 400, margin: '0 0 10px', color: INK, letterSpacing: '-0.01em' }}>
                Where the agent spends its time.
              </h3>
              <p className="text-[14px] leading-[1.7] mb-[18px]" style={{ color: INK_SOFT, maxWidth: 580 }}>
                {hasLivePerf
                  ? `Latency budget per layer, last ${perfAggregates!.turn_count} ${perfAggregates!.turn_count === 1 ? 'turn' : 'turns'} this session. Live p50 from services/performance_log.`
                  : 'Latency budget per panel, last 100 turns. The Postgres reads are fast. The LLM calls are everything else.'}
              </p>
              <div className="flex flex-col gap-[10px]" data-testid="perf-layer-rows">
                {(() => {
                  // Stub rows stay the source of truth when no live
                  // data has been captured yet. Live rows are derived
                  // from the chat.py ``timing`` dict: fastpath, intent,
                  // skill_router, orchestrator, specialist, tools,
                  // stream. 'tools' is further split against per-tool
                  // p50s when we have them so attendees can see which
                  // individual tool is expensive.
                  const stubRows = [
                    { label: 'LLM · OPUS · SYNTHESIZE', ms: 3779, pct: 92, llm: true },
                    { label: 'LLM · HAIKU · INTENT',    ms: 1887, pct: 46, llm: true },
                    { label: 'TOOL REGISTRY · DISCOVER', ms: 817, pct: 20, llm: false },
                    { label: 'MEMORY · EPISODIC',        ms: 55,  pct: 1.5, llm: false },
                    { label: 'MEMORY · PROCEDURAL',      ms: 13,  pct: 0.4, llm: false },
                    { label: 'MEMORY · SEMANTIC',        ms: 4,   pct: 0.1, llm: false },
                  ]
                  if (!hasLivePerf) return stubRows.map(row => ({ ...row, key: row.label }))

                  const layers = perfAggregates!.layers_p50 || {}
                  const layerEntries = [
                    { key: 'orchestrator', label: 'LLM · ORCHESTRATOR', llm: true },
                    { key: 'intent',       label: 'ROUTER · INTENT',    llm: true },
                    { key: 'skill_router', label: 'SKILLS · ROUTE',     llm: true },
                    { key: 'tools',        label: 'TOOLS · ALL',        llm: false },
                    { key: 'stream',       label: 'STREAM · TOKENS',    llm: false },
                    { key: 'fastpath',     label: 'FASTPATH · TRIAGE',  llm: false },
                  ]
                  const rows = layerEntries
                    .map(e => ({
                      key: e.key,
                      label: e.label,
                      llm: e.llm,
                      ms: Math.round(layers[e.key] ?? 0),
                    }))
                    .filter(r => r.ms > 0)
                  const maxMs = Math.max(1, ...rows.map(r => r.ms))
                  return rows.map(r => ({
                    ...r,
                    pct: (r.ms / maxMs) * 100,
                  }))
                })().map((row) => (
                  <div key={row.key ?? row.label} className="grid items-center gap-3 text-[12px]" style={{ gridTemplateColumns: '220px 1fr 60px' }}>
                    <span className="font-mono text-[11px]" style={{ color: INK }}>{row.label}</span>
                    <div className="h-2 rounded overflow-hidden" style={{ background: 'rgba(45, 24, 16, 0.06)' }}>
                      <div className="h-full rounded" style={{ width: `${Math.max(row.pct, 0.5)}%`, background: row.llm ? ACCENT : INK_SOFT }} />
                    </div>
                    <span className="font-mono text-right" style={{ color: INK }}>{row.ms}ms</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-3 text-[12px] italic" style={{ borderTop: '1px solid rgba(45, 24, 16, 0.08)', color: INK_QUIET }}>
                Postgres reads in single-digit milliseconds. LLM calls dominate. Where the agent spends its time is where you tune first.
              </div>
            </div>

            {/* iii. pgvector — index comparison */}
            <div className="rounded-xl" style={{ background: 'white', border: '1px solid rgba(45, 24, 16, 0.12)', padding: '22px 24px' }}>
              <div className="flex justify-between items-start mb-[14px]">
                <span style={{ fontFamily: 'Fraunces, Georgia, serif', fontStyle: 'italic', fontSize: 18, color: INK_QUIET }}>iii.</span>
                <span className="text-[10px] font-medium uppercase px-[10px] py-1 rounded" style={{ background: '#EAF3DE', color: '#27500A', letterSpacing: '0.16em' }}>pgvector</span>
              </div>
              <h3 style={{ fontFamily: 'Fraunces, Georgia, serif', fontSize: 22, fontWeight: 400, margin: '0 0 10px', color: INK, letterSpacing: '-0.01em' }}>
                Index strategy - recall vs latency.
              </h3>
              <p className="text-[14px] leading-[1.7] mb-[18px]" style={{ color: INK_SOFT, maxWidth: 580 }}>
                Three index strategies on the product_catalog embedding column. HNSW wins on the latency/recall tradeoff for this workload, but it's not free - build time and memory cost real money.
              </p>
              {/* Table */}
              <div className="rounded-md overflow-hidden mb-[14px]" style={{ background: 'rgba(45, 24, 16, 0.1)' }}>
                <div className="grid font-mono text-[10px] uppercase" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: 1 }}>
                  {['strategy', 'p50 latency', 'recall@10', 'build time'].map((h) => (
                    <div key={h} className="px-3 py-[9px]" style={{ background: CREAM_WARM, color: INK_SOFT, letterSpacing: '0.14em', textAlign: h === 'strategy' ? 'left' : 'right' }}>{h}</div>
                  ))}
                  {/* HNSW row */}
                  <div className="px-3 py-[11px] font-mono" style={{ background: 'white', color: INK }}>
                    HNSW <span className="text-[9px] font-medium uppercase ml-1 px-1.5 py-0.5 rounded-[3px]" style={{ background: '#EAF3DE', color: '#27500A', letterSpacing: '0.14em' }}>Shipped</span>
                  </div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK }}>4ms</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK }}>0.97</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK }}>42s</div>
                  {/* IVFFlat row */}
                  <div className="px-3 py-[11px] font-mono" style={{ background: 'white', color: INK_SOFT }}>IVFFlat</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>11ms</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>0.89</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>8s</div>
                  {/* Sequential scan row */}
                  <div className="px-3 py-[11px] font-mono" style={{ background: 'white', color: INK_SOFT }}>Sequential scan</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>340ms</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>1.00</div>
                  <div className="px-3 py-[11px] font-mono text-right" style={{ background: 'white', color: INK_SOFT }}>—</div>
                </div>
              </div>
              <div className="font-mono text-[11px] leading-[1.7] rounded-md mb-[14px]" style={{ background: CREAM_WARM, color: INK, padding: '11px 14px' }}>
                <div><span style={{ color: ACCENT }}>CREATE INDEX</span> ON product_catalog</div>
                <div><span style={{ color: ACCENT }}>USING</span> hnsw (embedding vector_cosine_ops);</div>
              </div>
            </div>

            {/* iv–vi. Inline pgvector benchmark sections — each is a
                self-contained accordion with its own API calls. Start
                collapsed so the tab isn't overwhelming; expand any to
                run live comparisons against the Aurora catalog. */}
            <HnswBenchmarkSection />
            <QuantizationSection />
            <IterativeScanSection />
          </div>
        )}
      </div>
    </div>
  )

  const chatArea = (
    <div className="h-full min-w-0">
      <WorkshopChat
        onEvents={setEvents}
        onSession={setSessionInfo}
        onOpenTrace={handleOpenTrace}
      />
    </div>
  )

  const detailArea = detailOpen && true && (
    <motion.div
      key={detailPanel}
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className="h-full min-w-0"
      data-testid="detail-panel-slot"
    >
      {renderDetail()}
    </motion.div>
  )

  return (
    <div
      className="workshop-surface min-h-screen flex flex-col"
      style={{ background: CREAM, color: INK }}
    >
      <AtelierSpotlight />

      {/* Global header chrome — wordmark + SurfaceToggle (Boutique /
          Atelier) + Account + Bag. Mounted on every route, including
          ``/workshop``, so the top navigation stays consistent and
          the surface-switch toggle has a permanent home. */}
      <Header
        current="home"
      />

      {/* Editorial hero + atmosphere ticker + live metrics row,
          full-width above the chat/tabs split. The cream-warm
          background on the hero zone deepens the magazine feel: the
          white metric cards and white panel cards in the split below
          get to pop against the warmer band. */}
      <div
        data-testid="atelier-header-zone"
        style={{
          background: CREAM_WARM,
          borderBottom: `1px solid ${INK_QUIET}30`,
        }}
      >
        <AtelierHero />
        <AtmosphereStrip
          skillCount={metrics.skillCount}
          medianMs={metrics.medianMs}
        />
        <MetricsRow
          skillCount={metrics.skillCount}
          elapsedMs={metrics.elapsedMs}
          toolsUsed={metrics.toolsUsed}
          confidencePercent={metrics.confidencePercent}
        />
      </div>

      {/* Main — responsive three-band layout */}
      <main
        className="flex-1 px-4 md:px-6 py-5 min-h-0"
        data-testid="workshop-main"
        data-layout={isLaptop ? 'three-zone' : isTablet ? 'tablet-overlay' : 'vertical-stack'}
      >
        {isLaptop ? (
          <PanelGroup
            orientation="horizontal"
            className="h-[calc(100vh-420px)] min-h-[480px] flex"
          >
            <Panel defaultSize={detailOpen ? '30%' : '42%'} minSize="22%">
              {chatArea}
            </Panel>
            <PanelResizeHandle
              className="w-1.5 transition-colors hover:bg-[rgba(0,0,0,0.05)]"
              style={{ background: `${INK_QUIET}20` }}
            />
            <Panel defaultSize={detailOpen ? '30%' : '58%'} minSize="22%">
              {workArea}
            </Panel>
            <AnimatePresence>
              {detailArea && (
                <>
                  <PanelResizeHandle
                    className="w-1.5 transition-colors hover:bg-[rgba(0,0,0,0.05)]"
                    style={{ background: `${INK_QUIET}20` }}
                  />
                  <Panel defaultSize="40%" minSize="28%">
                    {detailArea}
                  </Panel>
                </>
              )}
            </AnimatePresence>
          </PanelGroup>
        ) : isTablet ? (
          <div className="relative h-[calc(100vh-420px)] min-h-[480px] grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-4">
            {chatArea}
            <div className="relative min-w-0">
              {workArea}
              <AnimatePresence>
                {detailArea && (
                  <motion.div
                    initial={{ opacity: 0, x: 24 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 24 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                    className="absolute inset-0 z-10"
                    data-testid="detail-panel-tablet-overlay"
                  >
                    {renderDetail()}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="min-h-[520px]">{chatArea}</div>
            <div className="min-h-[520px]">{workArea}</div>
            {detailOpen && true && (
              <div className="min-h-[520px]" data-testid="detail-panel-stacked">
                {renderDetail()}
              </div>
            )}
          </div>
        )}
      </main>

      <Footer />

      {/* IndexPerformanceDashboard removed — pgvector benchmarks are
          now inline in the Performance tab via HnswBenchmarkSection,
          QuantizationSection, and IterativeScanSection. */}
    </div>
  )
}

/* ---- Architecture detail wrapper ----
 *
 * Shared shell for the new architecture detail pages (Memory, MCP,
 * Tool Registry, State Management, Runtime, Evaluations). Matches the
 * SkillsDetailWrapper footprint so it slots into the same resizable
 * panel. The page body (children) is one of the atelier-arch/*
 * components, which each call DetailPageShell internally for the
 * crumb + title + meta strip.
 */
function ArchDetailWrapper({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  return (
    <section
      data-testid={`arch-detail-${title.toLowerCase().replace(/\s+/g, '-')}`}
      className="h-full flex flex-col overflow-hidden rounded-2xl"
      style={{ background: 'var(--cream-2)', border: `1px solid ${INK_QUIET}30` }}
    >
      <div
        className="flex items-center justify-between px-5 py-[14px] text-[10px] uppercase font-medium flex-shrink-0"
        style={{
          background: 'var(--cream-1)',
          borderBottom: `1px solid ${INK_QUIET}20`,
          color: 'var(--red-1)',
          letterSpacing: '0.16em',
        }}
      >
        <span>Atelier · Architecture · {title}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label={`close ${title.toLowerCase()} panel`}
          className="px-2 py-1 rounded-md transition-colors hover:bg-[rgba(0,0,0,0.04)] normal-case tracking-normal text-[11px]"
          style={{ color: 'var(--ink-3)', letterSpacing: 0 }}
        >
          Close ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
    </section>
  )
}

/* ---- Skills detail wrapper ----
 *
 * Matches the other detail-panel component shape (a container with a
 * header + close button) so it slots into the same resizable panel
 * slot as the ArchDetailWrapper used by the other arch pages. The
 * SkillsPanel body is the canonical architecture view from Phase 4.
 */
function SkillsDetailWrapper({
  onClose,
  routing,
}: {
  onClose: () => void
  routing: SkillRouting | null
}) {
  return (
    <section
      data-testid="skills-detail"
      className="h-full flex flex-col overflow-hidden rounded-2xl"
      style={{ background: 'var(--cream-2)', border: `1px solid ${INK_QUIET}30` }}
    >
      <div
        className="flex items-center justify-between px-5 py-[14px] text-[10px] uppercase font-medium flex-shrink-0"
        style={{
          background: 'var(--cream-1)',
          borderBottom: `1px solid ${INK_QUIET}20`,
          color: 'var(--red-1)',
          letterSpacing: '0.16em',
        }}
      >
        <span>Atelier · Architecture · Skills</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="close skills panel"
          className="px-2 py-1 rounded-md transition-colors hover:bg-[rgba(0,0,0,0.04)] normal-case tracking-normal text-[11px]"
          style={{ color: 'var(--ink-3)', letterSpacing: 0 }}
        >
          Close ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <SkillsPanel
          routing={routing}
          userMessage={routing?.user_message ?? null}
        />
      </div>
    </section>
  )
}

export default function WorkshopPage() {
  return (
    <AuthGate>
      <WorkshopContent />
    </AuthGate>
  )
}
