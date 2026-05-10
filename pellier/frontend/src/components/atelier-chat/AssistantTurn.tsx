/**
 * AssistantTurn — composes one agent reply from a Turn primitive.
 *
 * Keeps the interleave logic in one place so WorkshopChat's JSX stays
 * clean. The render order is fixed:
 *
 *   1. PlanPreviewChip (if plan)
 *   2. ToolChips for each non-special panel (in emission order)
 *   3. AssistantText (the actual reply)
 *   4. ProductMiniCard grid (if recommendation picks)
 *   5. ConfidenceSummary (if MEMORY · CONFIDENCE panel emitted)
 *
 * Citation plumbing is wired here via ``onOpenTrace`` so the parent
 * can scroll the telemetry tab to a matching panel. Plan-chip,
 * tool-chip "Open in trace", and inline citation pills all flow
 * through the same callback. The synthesis prompt that emits inline
 * citations is a follow-up (see docs/backlog.md); the
 * infrastructure is in place.
 */
import type { Turn, WorkshopPanelEvent } from '../../services/workshop'
import AssistantText from './AssistantText'
import ConfidenceSummary from './ConfidenceSummary'
import PlanPreviewChip from './PlanPreviewChip'
import ProductMiniCard from './ProductMiniCard'
import ToolChip from './ToolChip'

export interface AssistantTurnProps {
  turn: Turn
  /** Click on a "view trace" / "Open in trace" / citation pill. */
  onOpenTrace?: (traceRef: string) => void
}

/**
 * Short, human-friendly chip label per tool tag. Falls back to the
 * panel's ``title`` field so tools that don't have a specific label
 * still read.
 *
 * Expand this map per-tool as copy gets tuned. Per-tool overrides
 * are intentionally centralized here rather than scattered across
 * backend emitters — they're frontend-display concerns.
 */
const TOOL_LABEL: Record<string, string> = {
  'TOOL · SEARCH': 'Searched product catalog',
  'TOOL · CHECK_INVENTORY': 'Checked inventory',
  'TOOL REGISTRY · DISCOVER': 'Discovered tools',
  'MEMORY · EPISODIC': 'Pulled your order history',
  'MEMORY · PROFILE': 'Pulled your preferences',
  'MEMORY · PROCEDURAL': 'Ranked by similar customers',
  'MEMORY · SEMANTIC': 'Matched against the catalog',
}

function labelForPanel(panel: WorkshopPanelEvent): string {
  return TOOL_LABEL[panel.tag] ?? panel.title
}

export default function AssistantTurn({ turn, onOpenTrace }: AssistantTurnProps) {
  return (
    <div data-testid="assistant-turn" className="flex flex-col">
      {turn.plan && (
        <PlanPreviewChip
          stepCount={turn.plan.steps.length}
          stepNames={turn.plan.steps.map(shortenStep)}
          onViewTrace={() => onOpenTrace?.('plan')}
        />
      )}
      {turn.panels.map((p, i) => (
        <ToolChip
          key={`${p.tag}-${p.ts_ms}-${i}`}
          panel={p}
          actionLabel={labelForPanel(p)}
          onOpenTrace={() => onOpenTrace?.(p.tag)}
        />
      ))}
      {turn.assistant_text !== null && (
        <AssistantText
          text={turn.assistant_text}
          citations={turn.citations}
          onCitationClick={onOpenTrace}
        />
      )}
      {turn.products && turn.products.length > 0 && (
        <div
          data-testid="assistant-turn-products"
          className="grid gap-2 mb-4"
          style={{
            gridTemplateColumns: `repeat(${Math.min(turn.products.length, 3)}, minmax(0, 1fr))`,
          }}
        >
          {turn.products.slice(0, 3).map((p, i) => (
            <ProductMiniCard
              key={p.product_id ?? `${p.name}-${i}`}
              name={p.name}
              price={p.price}
              attributes={p.attributes}
              tone={p.tone}
            />
          ))}
        </div>
      )}
      <ConfidenceSummary panel={turn.confidence} />
    </div>
  )
}

/**
 * Shorten a plan step string to a verb/noun token for the PLAN chip.
 *
 * The PLAN panel rendered on the right has the full step text; the
 * inline chip is a glance-read so only the first 1–2 words survive.
 */
function shortenStep(full: string): string {
  return full.split(/\s+·\s+|,|\.\s/, 1)[0].trim().split(/\s+/).slice(0, 2).join(' ')
}
