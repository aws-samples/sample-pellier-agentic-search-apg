/**
 * ToolChip — collapsed / expanded card representing one tool call
 * in the assistant's turn.
 *
 * Shape is uniform across tool types. The summary is a generic
 * template ("— N results · Tms") driven by panel metadata; if a
 * panel's rows are empty (e.g. a LLM panel with only `meta`), the
 * summary falls back to truncated meta text.
 *
 * Expanded state renders whatever panel data exists — SQL preview,
 * first couple of rows, meta — so SQL tools and meta-only LLM tools
 * share the same component.
 *
 * The chip does NOT subscribe to the telemetry tab directly. It
 * carries an optional ``onOpenTrace`` click handler that the parent
 * can wire to scroll + flash-highlight the matching panel on the
 * right rail.
 */
import { useState } from 'react'
import type { WorkshopPanelEvent } from '../../services/workshop'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'
const CREAM_WARM = '#f5e8d3'

export interface ToolChipProps {
  /** The panel event this chip represents. */
  panel: WorkshopPanelEvent
  /** Optional human-friendly label ("Searched catalog"); falls back to the panel title. */
  actionLabel?: string
  /** Start expanded. Default collapsed. */
  defaultExpanded?: boolean
  /** Click on "Open in trace ↗" (shown only in expanded state). */
  onOpenTrace?: () => void
}

/**
 * Default summary template: "— N result(s)" when the panel returns
 * rows; otherwise truncate the meta field (HTML stripped). Tools that
 * want richer phrasing can pass it via ``summary`` prop in a future
 * iteration.
 */
function defaultSummary(panel: WorkshopPanelEvent): string {
  if (panel.rows && panel.rows.length > 0) {
    const n = panel.rows.length
    return `— ${n} ${n === 1 ? 'result' : 'results'}`
  }
  if (panel.meta) {
    const plain = panel.meta.replace(/<[^>]+>/g, '').trim()
    return plain.length > 60 ? `— ${plain.slice(0, 57)}…` : `— ${plain}`
  }
  return ''
}

export default function ToolChip({
  panel,
  actionLabel,
  defaultExpanded = false,
  onOpenTrace,
}: ToolChipProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const label = actionLabel ?? panel.title
  const summary = defaultSummary(panel)
  return (
    <div
      data-testid={`tool-chip-${panel.tag}`}
      data-expanded={expanded ? 'true' : 'false'}
      className="rounded-lg mb-1.5 overflow-hidden"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.1)',
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-[10px] w-full px-[13px] py-[9px] text-left text-[12px] transition-colors hover:bg-[rgba(0,0,0,0.02)]"
        style={{
          color: INK,
          borderBottom: expanded ? '1px solid rgba(45, 24, 16, 0.06)' : 'none',
        }}
      >
        <span
          className="text-[9px]"
          style={{ color: expanded ? ACCENT : INK_QUIET }}
          aria-hidden
        >
          {expanded ? '▼' : '▶'}
        </span>
        <span style={{ color: INK, fontWeight: expanded ? 500 : 400 }}>{label}</span>
        {summary && (
          <span className="italic" style={{ color: INK_QUIET }}>
            {summary}
          </span>
        )}
        <span
          className="ml-auto font-mono text-[10px]"
          style={{ color: INK_QUIET }}
        >
          {panel.duration_ms}ms
        </span>
      </button>
      {expanded && (
        <div className="px-[13px] py-[11px]">
          {panel.sql && (
            <pre
              className="font-mono text-[11px] leading-[1.7] rounded-[5px] overflow-hidden whitespace-pre-wrap break-words"
              style={{
                background: CREAM_WARM,
                color: INK,
                padding: '9px 11px',
                marginBottom: 9,
                maxHeight: '4.5em',
              }}
            >
              {panel.sql.split('\n').slice(0, 2).join('\n')}
              {panel.sql.split('\n').length > 2 ? '\n···' : ''}
            </pre>
          )}
          {panel.rows && panel.rows.length > 0 && (
            <div
              className="font-mono text-[11px] mb-2"
              style={{ color: INK_SOFT }}
            >
              {panel.rows.slice(0, 3).map((row, i) => (
                <div key={i} className="truncate">
                  {row.join(' · ')}
                </div>
              ))}
              {panel.rows.length > 3 && (
                <div style={{ color: INK_QUIET }}>
                  + {panel.rows.length - 3} more
                </div>
              )}
            </div>
          )}
          <div className="flex justify-between items-center text-[11px]">
            {panel.meta ? (
              <span
                className="italic"
                style={{ color: INK_QUIET }}
                dangerouslySetInnerHTML={{ __html: panel.meta }}
              />
            ) : (
              <span />
            )}
            {onOpenTrace && (
              <button
                type="button"
                data-testid={`tool-chip-open-trace-${panel.tag}`}
                onClick={(e) => {
                  e.stopPropagation()
                  onOpenTrace()
                }}
                className="transition-opacity hover:opacity-75"
                style={{ color: ACCENT }}
              >
                Open in trace ↗
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
