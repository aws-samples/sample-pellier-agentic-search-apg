/**
 * The compact list of what Pellier did this turn.
 *
 * Each step shows its plain label, a ring while it runs, a check when its
 * tool returns, and the one-line finding the backend computed. With the
 * Builder view on, every step adds its layer tags and a mono evidence line,
 * and a search adds "How it ranked": the full panel by default, or whatever
 * `renderRanking` draws (the storefront dock draws a one-line summary that
 * points at the page's panel). After the answer, the list folds to one line
 * the shopper can open. On phone widths only the active step shows its
 * detail while the turn runs.
 *
 * Every tool use is its own step, however many a turn runs. To stay short,
 * the list can show only the latest few (`latest`) and collapse the earlier
 * ones behind "Show N earlier steps". It collapses, never merges: each step
 * keeps its own finding and evidence.
 */
import { useId, useState, type ReactNode } from 'react'
import { Check, ChevronRight, CircleAlert } from 'lucide-react'
import LayerTag from './LayerTag'
import RankingPanel from './RankingPanel'
import { evidenceLine } from './evidence'
import type { RankingPayload, TurnStep } from './turnTypes'

export interface StepListProps {
  steps: TurnStep[]
  /** The turn is still running. */
  live: boolean
  builderView: boolean
  /** Fold to one line the shopper can open. */
  folded?: boolean
  /** The fold's one line. Defaults to "How Pellier answered, N steps". */
  summary?: string
  defaultOpen?: boolean
  className?: string
  /** Draws a search's ranking in Builder view; defaults to the full panel. */
  renderRanking?: (ranking: RankingPayload) => ReactNode
  /** Show only the latest this many steps, the earlier ones behind one control. Unset shows all. */
  latest?: number
}

function StepIcon({ status }: { status: TurnStep['status'] }) {
  if (status === 'running') return <span className="tn-ring" aria-hidden="true" />
  if (status === 'failed') return <CircleAlert size={14} strokeWidth={2} aria-hidden="true" />
  return <Check size={14} strokeWidth={2} aria-hidden="true" />
}

function statusWord(status: TurnStep['status']): string {
  if (status === 'running') return 'in progress'
  if (status === 'failed') return 'did not complete'
  return 'done'
}

export function foldSummary(count: number): string {
  return `How Pellier answered, ${count} ${count === 1 ? 'step' : 'steps'}`
}

export function earlierSummary(count: number): string {
  return `Show ${count} earlier ${count === 1 ? 'step' : 'steps'}`
}

export const HIDE_EARLIER = 'Hide earlier steps'

export default function StepList({
  steps,
  live,
  builderView,
  folded = false,
  summary,
  defaultOpen = false,
  className,
  renderRanking = ranking => <RankingPanel ranking={ranking} />,
  latest,
}: StepListProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [showEarlier, setShowEarlier] = useState(false)
  const listId = useId()
  if (steps.length === 0) return null
  const earlier = latest === undefined ? 0 : Math.max(0, steps.length - latest)
  const shown = showEarlier ? steps : steps.slice(earlier)
  const list = (
    <>
      {earlier > 0 && (
        <button
          type="button"
          className="tn-earlier"
          aria-expanded={showEarlier}
          aria-controls={listId}
          onClick={() => setShowEarlier(value => !value)}
          data-testid="turn-earlier"
        >
          <span>{showEarlier ? HIDE_EARLIER : earlierSummary(earlier)}</span>
          <ChevronRight size={12} strokeWidth={2} className="tn-chev" aria-hidden="true" />
        </button>
      )}
      <ol
        id={listId}
        className={['tn-steps', className ?? ''].filter(Boolean).join(' ')}
        data-live={live ? 'true' : 'false'}
        data-builder={builderView ? 'on' : 'off'}
        data-testid="turn-steps"
      >
        {shown.map(step => {
          const ranking = step.builder?.ranking
          const evidence = builderView ? evidenceLine(step) : ''
          return (
            <li key={step.id} className="tn-step" data-status={step.status} data-testid="turn-step">
              <span className="tn-step-ico" data-status={step.status}>
                <StepIcon status={step.status} />
                <span className="gov-visually-hidden">{statusWord(step.status)}</span>
              </span>
              <span className="tn-step-body">
                <span className="tn-step-line">
                  <span className="tn-step-label">{step.label}</span>
                  {builderView && step.tags.map(tag => <LayerTag key={tag}>{tag}</LayerTag>)}
                </span>
                {step.finding && <span className="tn-finding">{step.finding}</span>}
                {evidence && (
                  <span className="tn-evidence" data-testid="turn-evidence">{evidence}</span>
                )}
                {builderView && ranking && step.status !== 'running' && renderRanking(ranking)}
              </span>
            </li>
          )
        })}
      </ol>
    </>
  )
  if (!folded) return list
  return (
    <div className="tn-fold">
      <button
        type="button"
        className="tn-summary"
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        data-testid="turn-fold"
      >
        <Check size={14} strokeWidth={2} aria-hidden="true" />
        <span>{summary ?? foldSummary(steps.length)}</span>
        <ChevronRight size={12} strokeWidth={2} className="tn-chev" aria-hidden="true" />
      </button>
      {open && list}
    </div>
  )
}
