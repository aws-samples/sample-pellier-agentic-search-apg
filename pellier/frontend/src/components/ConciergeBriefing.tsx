/**
 * ConciergeBriefing — shift-handover greeting for the concierge modal.
 *
 * Renders as the modal's empty-state hero (before the first user
 * message). Replaces the blank chat opening with a first-person agent
 * briefing:
 *   - Time-of-day greeting with first-name (anonymous fallback is
 *     still warm).
 *   - Paragraph with inline chips (cited stats + product picks + the
 *     ``stub`` preview chip for pre-vetted picks).
 *   - Three action pills that pre-compose a concierge query via the
 *     parent-supplied ``onAction`` callback — reuses the same path
 *     the hero SearchPill uses.
 *
 * Dismissal is session-scoped via an internal state flag; the parent
 * typically un-mounts the component on first user message. localStorage
 * is intentionally NOT used — stickiness across visits would make the
 * feature invisible after day two.
 *
 * Data: ``GET /api/storefront/briefing``. Never 5xx — backend degrades
 * to generic copy if DB is down.
 */
import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const ACCENT = '#c44536'

type SourceTag = 'real' | 'stub' | 'partial'

interface BriefingChip {
  label: string
  kind: 'stat' | 'product' | 'category'
  meaning?: string
  product_id?: string
  source: SourceTag
}

interface BriefingAction {
  id: string
  label: string
  primary?: boolean
}

interface BriefingResponse {
  greeting: string
  line: string
  chips: BriefingChip[]
  actions: BriefingAction[]
  generated_at: string
}

export interface ConciergeBriefingProps {
  /** Fired when the user clicks an action pill. The parent should
   *  pre-compose a concierge query and dispatch it through the same
   *  ``openConciergeWithQuery`` path the hero SearchPill uses. */
  onAction: (actionId: string, label: string) => void
  /** Optional — fired when a product chip is clicked, so the parent
   *  can open the product modal or scroll the grid. */
  onProductChip?: (productId: string) => void
}

const CHIP_STYLES: Record<SourceTag, { bg: string; border: string; fg: string }> = {
  real: {
    bg: 'rgba(255,255,255,0.8)',
    border: `${INK_QUIET}50`,
    fg: INK,
  },
  stub: {
    bg: '#fef3c7',
    border: '#fcd34d',
    fg: '#b45309',
  },
  partial: {
    bg: CREAM_WARM,
    border: `${INK_QUIET}40`,
    fg: INK_SOFT,
  },
}

export default function ConciergeBriefing({
  onAction,
  onProductChip,
}: ConciergeBriefingProps) {
  const [data, setData] = useState<BriefingResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchBriefing = useCallback(async (signal?: AbortSignal) => {
    try {
      const token = localStorage.getItem('pellier-access-token')
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(`${API_BASE_URL}/api/storefront/briefing`, {
        headers,
        signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData((await res.json()) as BriefingResponse)
    } catch (e) {
      if ((e as { name?: string })?.name === 'AbortError') return
      setError(e instanceof Error ? e.message : 'unknown error')
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetchBriefing(controller.signal)
    return () => controller.abort()
  }, [fetchBriefing])

  if (error && !data) {
    // Degraded: the backend never 5xxs but the network might. Render
    // a quiet fallback rather than nothing — the briefing is the
    // empty-state; its absence would break the "something's here" feel.
    return (
      <div
        data-testid="concierge-briefing-fallback"
        className="flex flex-col items-center text-center gap-2 px-6 py-10"
      >
        <Sparkles className="w-6 h-6" style={{ color: INK_QUIET }} />
        <p className="text-sm" style={{ color: INK_SOFT }}>
          What are you looking for today?
        </p>
      </div>
    )
  }

  if (!data) {
    return <BriefingSkeleton />
  }

  return (
    <motion.section
      data-testid="concierge-briefing"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="px-6 py-6 flex flex-col gap-4"
    >
      <div className="flex items-start gap-3">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 mt-1"
          style={{ background: `${ACCENT}15`, border: `1px solid ${ACCENT}40` }}
        >
          <Sparkles className="w-4 h-4" style={{ color: ACCENT }} />
        </div>
        <div className="flex-1 min-w-0">
          <h2
            data-testid="concierge-briefing-greeting"
            className="text-[22px] leading-[1.2]"
            style={{
              color: INK,
              fontFamily: "'Instrument Serif', Georgia, serif",
              fontWeight: 400,
            }}
          >
            {data.greeting}
          </h2>
          <p
            className="mt-2 text-[14px] leading-[1.65]"
            style={{ color: INK_SOFT }}
            data-testid="concierge-briefing-line"
          >
            {renderLineWithChips(data.line, data.chips, onProductChip)}
          </p>
        </div>
      </div>

      {/* Stub chips that didn't land inline still render below so the
          scaffolding is visible. */}
      {data.chips.some((c) => c.source === 'stub') && (
        <div className="flex flex-wrap gap-2 pl-12">
          {data.chips
            .filter((c) => c.source === 'stub')
            .map((chip, i) => (
              <Chip
                key={`stub-${i}`}
                chip={chip}
                onProductChip={onProductChip}
              />
            ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pl-12">
        {data.actions.map((action) => (
          <button
            key={action.id}
            type="button"
            data-testid={`briefing-action-${action.id}`}
            onClick={() => onAction(action.id, action.label)}
            className="px-3.5 py-1.5 rounded-full text-[12.5px] font-medium transition-opacity hover:opacity-85"
            style={
              action.primary
                ? { background: INK, color: CREAM }
                : {
                    background: 'rgba(255,255,255,0.8)',
                    color: INK,
                    border: `1px solid ${INK_QUIET}40`,
                  }
            }
          >
            {action.label}
          </button>
        ))}
      </div>
    </motion.section>
  )
}

/**
 * Render a briefing line with ``stat`` / ``product`` chip labels
 * promoted to inline chips. Matches the first occurrence of each chip
 * label in the line and wraps it in a Chip component; unmatched chip
 * entries fall back to the stub row below.
 *
 * Keeps it simple: label-as-needle substring match. The backend line
 * is composed with the chip labels verbatim, so match rate is 100%
 * for the real + partial chips today. Stub chips are typically
 * placeholder text that doesn't appear in the line — those stay in
 * the fallback row.
 */
function renderLineWithChips(
  line: string,
  chips: BriefingChip[],
  onProductChip?: (productId: string) => void,
): React.ReactNode {
  // Only chips whose label appears in the line become inline.
  const inlineChips = chips.filter(
    (c) => c.source !== 'stub' && line.includes(c.label),
  )

  if (inlineChips.length === 0) {
    return line
  }

  // Walk through the string, replacing the first occurrence of each
  // chip label. Later same-label collisions stay as plain text — the
  // briefing composer avoids repeating numeric labels.
  const nodes: React.ReactNode[] = []
  let cursor = 0
  let key = 0
  let remaining = line

  const seen = new Set<string>()
  while (remaining.length > 0) {
    const next = inlineChips
      .filter((c) => !seen.has(c.label))
      .map((c) => ({ chip: c, idx: remaining.indexOf(c.label) }))
      .filter((x) => x.idx >= 0)
      .sort((a, b) => a.idx - b.idx)[0]

    if (!next) {
      nodes.push(remaining)
      break
    }
    if (next.idx > 0) nodes.push(remaining.slice(0, next.idx))
    nodes.push(
      <Chip
        key={`chip-${key++}`}
        chip={next.chip}
        onProductChip={onProductChip}
      />,
    )
    seen.add(next.chip.label)
    remaining = remaining.slice(next.idx + next.chip.label.length)
    cursor += next.idx + next.chip.label.length
  }
  return nodes
}

function Chip({
  chip,
  onProductChip,
}: {
  chip: BriefingChip
  onProductChip?: (productId: string) => void
}) {
  const style = CHIP_STYLES[chip.source]
  const title =
    chip.meaning ??
    (chip.source === 'stub' ? 'Lights up when tool_audit writes land' : undefined)
  const clickable = chip.kind === 'product' && !!chip.product_id && !!onProductChip

  const content = (
    <span
      className="inline-flex items-center gap-1 font-mono text-[11.5px] px-1.5 py-0.5 rounded whitespace-nowrap"
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
        color: style.fg,
      }}
    >
      {chip.label}
      {chip.source === 'stub' && (
        <span
          aria-label="placeholder — lights up later"
          title="Placeholder — lights up when tool_audit writes are wired."
          className="w-1 h-1 rounded-full"
          style={{ background: style.fg }}
        />
      )}
    </span>
  )

  if (clickable) {
    return (
      <button
        type="button"
        data-testid={`briefing-chip-${chip.product_id}`}
        onClick={() => onProductChip!(chip.product_id!)}
        title={title}
        className="inline transition-opacity hover:opacity-80"
      >
        {content}
      </button>
    )
  }
  return (
    <span
      data-testid={`briefing-chip-${chip.kind}`}
      title={title}
      className="inline-block align-baseline mx-[1px]"
    >
      {content}
    </span>
  )
}

function BriefingSkeleton() {
  return (
    <div
      data-testid="concierge-briefing-skeleton"
      className="px-6 py-6 flex items-start gap-3"
    >
      <div
        className="w-9 h-9 rounded-xl flex-shrink-0"
        style={{ background: `${INK_QUIET}22` }}
      />
      <div className="flex-1 flex flex-col gap-2">
        <div
          className="h-5 w-48 rounded"
          style={{ background: `${INK_QUIET}22` }}
        />
        <div
          className="h-3 w-full rounded"
          style={{ background: `${INK_QUIET}18` }}
        />
        <div
          className="h-3 w-3/4 rounded"
          style={{ background: `${INK_QUIET}18` }}
        />
      </div>
    </div>
  )
}
