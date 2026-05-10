/**
 * MetricsRow — four live metric cards above the chat/tabs split.
 *
 * Four metrics read honestly from live state — "what's happening in
 * this session" is a better demo signal than system-wide counters:
 *
 *   SKILLS · this turn         latest skill routing's loaded_skills.length
 *   ELAPSED · this turn        last_event_ts - first_event_ts
 *   TOOLS USED · this turn     panel count with tag_class === 'cyan'
 *   CONFIDENCE · last reply    result value from MEMORY · CONFIDENCE
 *
 * Pre-turn empty states: SKILLS/TOOLS show 0, ELAPSED shows '—',
 * CONFIDENCE shows '—'. Once the first turn completes all four
 * resolve to real numbers.
 *
 * Skills is sourced from ``pellier-skill-routing-latest`` in
 * localStorage (written by the storefront chat's useAgentChat). The
 * Atelier workshop chat shares the same key so the Architecture tab's
 * Skills story gets a live dashboard number.
 */

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'

export interface MetricsRowProps {
  /** Loaded-skill count from the latest skill routing decision. */
  skillCount: number
  /** Elapsed wall-clock ms of the current turn, or null pre-turn. */
  elapsedMs: number | null
  /** Count of panel events whose tag_class === 'cyan' (data-op tools). */
  toolsUsed: number
  /** Confidence percent from the last MEMORY · CONFIDENCE panel, or null. */
  confidencePercent: number | null
}

export default function MetricsRow({
  skillCount,
  elapsedMs,
  toolsUsed,
  confidencePercent,
}: MetricsRowProps) {
  return (
    <div
      data-testid="metrics-row"
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-6 py-5"
    >
      <MetricCard
        id="skills"
        label="Skills"
        sublabel="this turn"
        value={skillCount}
        unit={null}
        emptyValue={0}
      />
      <MetricCard
        id="elapsed"
        label="Elapsed"
        sublabel="this turn"
        value={elapsedMs}
        unit={elapsedMs === null ? null : 'ms'}
        emptyValue="—"
      />
      <MetricCard
        id="tools-used"
        label="Tools used"
        sublabel="this turn"
        value={toolsUsed}
        unit={null}
        emptyValue={0}
      />
      <MetricCard
        id="confidence"
        label="Confidence"
        sublabel="last reply"
        value={confidencePercent}
        unit={confidencePercent === null ? null : '%'}
        emptyValue="—"
      />
    </div>
  )
}

interface MetricCardProps {
  id: string
  label: string
  sublabel: string
  value: number | string | null
  unit: string | null
  emptyValue: number | string
}

function MetricCard({ id, label, sublabel, value, unit, emptyValue }: MetricCardProps) {
  const display = value === null || value === undefined ? emptyValue : value
  return (
    <div
      data-testid={`metric-card-${id}`}
      className="rounded-lg"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.14)',
        padding: '14px 14px 12px',
      }}
    >
      <div
        className="font-mono text-[10px] uppercase mb-1.5"
        style={{ color: INK_QUIET, letterSpacing: '0.16em' }}
      >
        {label}
      </div>
      <div
        className="text-[26px] leading-[1]"
        style={{
          color: INK,
          fontFamily: "'Iowan Old Style', Georgia, 'Times New Roman', serif",
          fontStyle: 'italic',
          fontWeight: 400,
        }}
      >
        {display}
        {unit && (
          <span
            className="text-[14px] ml-0.5 font-sans"
            style={{ color: INK_QUIET, fontStyle: 'normal' }}
          >
            {unit}
          </span>
        )}
      </div>
      <div className="text-[11px] mt-1" style={{ color: INK_SOFT }}>
        {sublabel}
      </div>
    </div>
  )
}
