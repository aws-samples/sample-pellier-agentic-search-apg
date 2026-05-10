/**
 * PulseBar — ambient 4-metric strip above the hero on /.
 *
 * Pre-Week-3 "premium agentic" enhancement: gives the homepage a
 * heartbeat whether or not the shopper is interacting with the
 * concierge. Inspired by the DBA agent dashboard but dialed quieter —
 * this serves shoppers, not operators, so the strip defers visually.
 *
 * Rules:
 *   - 30s refresh while tab visible (AbortController + visibilitychange).
 *   - Each metric carries a ``source`` tag rendered as a 6px dot:
 *     real = quiet green, stub = warm amber, partial = grey.
 *     Tooltip on hover explains what's real vs pending.
 *   - Session-dismissible via the × on the right. Stays collapsed
 *     within the session — no localStorage so day-two visitors see
 *     it again (matches the briefing dismissal rule).
 *   - Homepage only — wiring is handled at ``HomePage.tsx``. Other
 *     routes don't mount this component until we get feedback.
 *
 * Data: ``GET /api/storefront/pulse`` returns ``{metrics, generated_at}``.
 * Never 5xx — the backend degrades to stub metrics if DB is down.
 */
import { useCallback, useEffect, useState } from 'react'
import { X } from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM_WARM = '#f5e8d3'

type SourceTag = 'real' | 'stub' | 'partial'

interface Metric {
  id: string
  label: string
  primary: string
  secondary: string
  source: SourceTag
}

interface PulseResponse {
  metrics: Metric[]
  generated_at: string
}

const SOURCE_COLORS: Record<SourceTag, { dot: string; tooltip: string }> = {
  real: {
    dot: '#047857',
    tooltip: 'Live data — read from Aurora this moment.',
  },
  stub: {
    dot: '#b45309',
    tooltip:
      'Placeholder — lights up once tool_audit writes are wired. Visible so you can see the scaffolding.',
  },
  partial: {
    dot: '#6b4a35',
    tooltip:
      'Partially live — reflects real numbers but resets on process restart. Persistence is in progress.',
  },
}

const REFRESH_MS = 30_000

export default function PulseBar() {
  const [metrics, setMetrics] = useState<Metric[] | null>(null)
  const [dismissed, setDismissed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const fetchPulse = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/storefront/pulse`, { signal })
      if (!res.ok) return
      const body = (await res.json()) as PulseResponse
      setMetrics(body.metrics)
      setLoaded(true)
    } catch (e) {
      // AbortError on unmount / visibility change is expected — swallow.
      if ((e as { name?: string })?.name !== 'AbortError') {
        console.warn('pulse fetch failed:', e)
      }
    }
  }, [])

  useEffect(() => {
    if (dismissed) return
    const controller = new AbortController()
    fetchPulse(controller.signal)

    let interval: ReturnType<typeof setInterval> | null = null
    const start = () => {
      if (interval) return
      interval = setInterval(() => fetchPulse(), REFRESH_MS)
    }
    const stop = () => {
      if (interval) clearInterval(interval)
      interval = null
    }

    // Only poll while the tab is visible — avoids spending embedding
    // cost counters ticking up when no one's looking.
    if (document.visibilityState === 'visible') start()
    const onVis = () => {
      if (document.visibilityState === 'visible') {
        fetchPulse()
        start()
      } else {
        stop()
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      controller.abort()
      stop()
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [dismissed, fetchPulse])

  if (dismissed) return null

  return (
    <section
      data-testid="pulse-bar"
      aria-label="Agent pulse"
      className="w-full"
      style={{
        background: CREAM_WARM,
        borderBottom: `1px solid ${INK_QUIET}25`,
      }}
    >
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-2.5 flex items-center gap-3">
        <span
          className="font-mono text-[10px] uppercase tracking-[1.5px] hidden md:inline"
          style={{ color: INK_QUIET }}
        >
          Agent pulse
        </span>
        <div
          data-testid="pulse-bar-grid"
          className="flex-1 grid grid-cols-2 lg:grid-cols-4 gap-x-5 gap-y-2"
        >
          {(metrics ?? Array.from({ length: 4 })).map((m, i) =>
            m ? (
              <PulseMetricCell key={m.id} metric={m as Metric} />
            ) : (
              <PulseSkeletonCell key={i} />
            ),
          )}
        </div>
        <button
          type="button"
          data-testid="pulse-bar-dismiss"
          aria-label="Dismiss agent pulse for this session"
          onClick={() => setDismissed(true)}
          className="p-1 rounded transition-colors hover:bg-[rgba(0,0,0,0.04)]"
          style={{ color: INK_QUIET }}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {/* a11y-only loaded flag so tests can assert without relying on DOM text */}
      <span data-testid="pulse-bar-loaded" data-loaded={loaded} className="sr-only" />
    </section>
  )
}

function PulseMetricCell({ metric }: { metric: Metric }) {
  const src = SOURCE_COLORS[metric.source]
  return (
    <div
      data-testid={`pulse-metric-${metric.id}`}
      data-source={metric.source}
      className="relative flex flex-col gap-0.5"
    >
      <div className="flex items-center gap-1.5">
        <span
          className="font-mono text-[10px] uppercase tracking-[1.3px]"
          style={{ color: INK_QUIET }}
        >
          {metric.label}
        </span>
        <span
          data-testid={`pulse-metric-${metric.id}-dot`}
          aria-label={src.tooltip}
          title={src.tooltip}
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: src.dot }}
        />
      </div>
      <span
        className="text-[15px] leading-[1.2] font-semibold truncate"
        style={{
          color: INK,
          fontFamily: "'Instrument Serif', Georgia, serif",
          fontWeight: 500,
        }}
      >
        {metric.primary}
      </span>
      <span className="text-[11px] leading-[1.3] truncate" style={{ color: INK_SOFT }}>
        {metric.secondary}
      </span>
    </div>
  )
}

function PulseSkeletonCell() {
  return (
    <div data-testid="pulse-metric-skeleton" className="flex flex-col gap-1.5">
      <div
        className="h-2 w-16 rounded"
        style={{ background: `${INK_QUIET}22` }}
      />
      <div
        className="h-4 w-28 rounded"
        style={{ background: `${INK_QUIET}18` }}
      />
      <div
        className="h-2 w-24 rounded"
        style={{ background: `${INK_QUIET}15` }}
      />
    </div>
  )
}
