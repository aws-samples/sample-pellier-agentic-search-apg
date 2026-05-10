/**
 * PlanPreviewChip — inline one-liner that previews the PLAN panel and
 * offers a "view trace" link that jumps the telemetry tab to the
 * matching PLAN card.
 *
 * Render: soft-blue pill with a PLAN tag, "N steps · step1 → step2 …"
 * in ink, terracotta "view trace ↗" link on the right.
 */

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'

export interface PlanPreviewChipProps {
  stepCount: number
  /** Short step labels in order (e.g. ["parse", "memory", "search"]). */
  stepNames: string[]
  /** Click → scroll the telemetry tab to the PLAN card + flash border. */
  onViewTrace?: () => void
}

export default function PlanPreviewChip({
  stepCount,
  stepNames,
  onViewTrace,
}: PlanPreviewChipProps) {
  const chainLabel = stepNames.join(' → ')
  return (
    <div
      data-testid="plan-preview-chip"
      className="inline-flex items-center gap-2 px-[11px] py-[6px] mb-4 rounded-full text-[11px]"
      style={{ background: 'rgba(195, 213, 244, 0.4)' }}
    >
      <span
        className="font-mono text-[9px] font-medium px-[7px] py-[1px] rounded uppercase"
        style={{
          color: '#0C447C',
          background: '#B5D4F4',
          letterSpacing: '0.12em',
        }}
      >
        PLAN
      </span>
      <span style={{ color: INK }}>{stepCount} steps</span>
      <span style={{ color: INK_SOFT }}>· {chainLabel}</span>
      <button
        type="button"
        data-testid="plan-preview-view-trace"
        onClick={onViewTrace}
        className="ml-1 transition-opacity hover:opacity-75"
        style={{ color: ACCENT }}
      >
        view trace ↗
      </button>
    </div>
  )
}
