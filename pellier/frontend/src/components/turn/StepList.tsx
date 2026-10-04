/**
 * The compact list of what Pellier did this turn.
 *
 * Each step shows its plain label, a ring while it runs, a check when its
 * tool returns, and the one-line finding the backend computed. With the
 * Builder view on, every step adds its layer tags and a mono evidence line,
 * and a search adds the "How it ranked" panel. After the answer, the list
 * folds to one line the shopper can open. On phone widths only the active
 * step shows its detail while the turn runs.
 */
import { useState } from 'react'
import { Check, ChevronRight, CircleAlert } from 'lucide-react'
import LayerTag from './LayerTag'
import RankingPanel from './RankingPanel'
import { evidenceLine } from './evidence'
import type { TurnStep } from './turnTypes'

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

export default function StepList({
  steps,
  live,
  builderView,
  folded = false,
  summary,
  defaultOpen = false,
  className,
}: StepListProps) {
  const [open, setOpen] = useState(defaultOpen)
  if (steps.length === 0) return null
  const list = (
    <ol
      className={['tn-steps', className ?? ''].filter(Boolean).join(' ')}
      data-live={live ? 'true' : 'false'}
      data-builder={builderView ? 'on' : 'off'}
      data-testid="turn-steps"
    >
      {steps.map(step => {
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
              {evidence && <span className="tn-evidence" data-testid="turn-evidence">{evidence}</span>}
              {builderView && ranking && step.status !== 'running' && (
                <RankingPanel ranking={ranking} />
              )}
            </span>
          </li>
        )
      })}
    </ol>
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
