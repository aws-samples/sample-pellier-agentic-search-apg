/**
 * CustomerCard — top-of-chat identity strip.
 *
 * White card, ink-at-12% border, 10px radius.
 * Left: 28px ink circle with italic serif initial + name + sublabel.
 * Right: monospace session id + "↻ New session" reset control.
 */
import { RotateCw } from 'lucide-react'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const CREAM = '#fbf4e8'

export interface CustomerCardProps {
  /** Display name. "Anonymous" renders the initial "A". */
  name: string
  /** Optional subline e.g. "3 prior orders · warm neutrals". */
  sublabel?: string
  /** Short session id; null → no id pill. */
  sessionId: string | null
  /** Reset fires the "↻ New session" control. */
  onReset: () => void
  /** Disable the reset while a request is mid-flight. */
  disabled?: boolean
}

export default function CustomerCard({
  name,
  sublabel,
  sessionId,
  onReset,
  disabled,
}: CustomerCardProps) {
  const initial = name.trim().charAt(0).toUpperCase() || 'A'
  return (
    <div
      data-testid="customer-card"
      className="flex justify-between items-center px-[14px] py-3 mb-5 rounded-[10px]"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.12)',
      }}
    >
      <div className="flex items-center gap-[10px]">
        <div
          aria-hidden
          className="w-7 h-7 rounded-full flex items-center justify-center text-[13px]"
          style={{
            background: INK,
            color: CREAM,
            fontFamily: "'Iowan Old Style', Georgia, 'Times New Roman', serif",
            fontStyle: 'italic',
          }}
        >
          {initial}
        </div>
        <div>
          <div className="text-[13px] font-medium" style={{ color: INK }}>
            {name}
          </div>
          {sublabel && (
            <div className="text-[10px]" style={{ color: INK_QUIET }}>
              {sublabel}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {sessionId && (
          <span
            className="font-mono text-[10px]"
            style={{ color: INK_QUIET }}
            title={sessionId}
          >
            {sessionId.slice(0, 8)}
          </span>
        )}
        <button
          type="button"
          data-testid="customer-card-reset"
          onClick={onReset}
          disabled={disabled}
          className="inline-flex items-center gap-1 text-[11px] transition-opacity hover:opacity-70 disabled:opacity-40"
          style={{ color: INK_SOFT }}
        >
          <RotateCw className="w-3 h-3" />
          New session
        </button>
      </div>
    </div>
  )
}
