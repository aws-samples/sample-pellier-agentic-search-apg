/**
 * ConfidenceSummary — closes each agent turn with a deterministic
 * confidence band (not LLM self-report).
 *
 * The number is whatever the ``MEMORY · CONFIDENCE`` panel's result
 * row resolves to — computed from upstream panel row coverage (picks
 * survived fact-check, customer history depth, top similarity). The
 * italic justification line echoes the panel's meta in shopper
 * language so the chat reader doesn't need to switch to the trace to
 * understand "why 94%".
 */
import type { WorkshopPanelEvent } from '../../services/workshop'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'

const GREEN_BG = 'rgba(192, 221, 151, 0.18)'
const GREEN_BORDER = 'rgba(99, 153, 34, 0.18)'
const GREEN_PILL_BG = '#C0DD97'
const GREEN_PILL_FG = '#27500A'

export interface ConfidenceSummaryProps {
  /** The MEMORY · CONFIDENCE panel from the turn, or undefined pre-turn. */
  panel: WorkshopPanelEvent | undefined
}

/**
 * Extract "94" from the panel's result row. Shape:
 *   rows: [
 *     ["base", "60"],
 *     ...
 *     ["result", "94 (clamped to [30, 98])"]
 *   ]
 */
function extractPercent(panel: WorkshopPanelEvent): number | null {
  const resultRow = panel.rows.find(
    (r) => r[0]?.toLowerCase() === 'result',
  )
  if (!resultRow || !resultRow[1]) return null
  const match = resultRow[1].match(/\d+/)
  return match ? parseInt(match[0], 10) : null
}

/** Strip any HTML in the meta (backend emits small inline <span>s). */
function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, '').trim()
}

export default function ConfidenceSummary({ panel }: ConfidenceSummaryProps) {
  if (!panel) return null
  const percent = extractPercent(panel)
  if (percent === null) return null
  const justification = stripTags(panel.meta)
  return (
    <div
      data-testid="confidence-summary"
      className="flex items-center gap-[10px] px-[13px] py-[10px] rounded-lg text-[12px] mb-6"
      style={{
        background: GREEN_BG,
        border: `1px solid ${GREEN_BORDER}`,
      }}
    >
      <span
        className="font-mono text-[9px] font-medium uppercase px-[7px] py-0.5 rounded"
        style={{
          background: GREEN_PILL_BG,
          color: GREEN_PILL_FG,
          letterSpacing: '0.14em',
        }}
      >
        Confidence
      </span>
      <span className="font-medium" style={{ color: INK }}>
        {percent}%
      </span>
      {justification && (
        <span
          className="italic text-[11px]"
          style={{ color: INK_SOFT }}
        >
          {justification}
        </span>
      )}
    </div>
  )
}
