/**
 * The investigation column: the graph's steps as they stream, the brief, and
 * the proposed credit with its three checks.
 *
 * Built from the same status, step and tag components as Ask Pellier, so the
 * Investigator and the Planner read exactly as the shopper's agents do. The
 * findings are computed by the backend from the real tool results; the brief
 * is the Investigator's own words, labelled as such.
 */
import React from 'react'
import { StatusLine, StepList, useBuilderView } from '../../components/turn'
import type { ReviewController } from '../hooks/useReview'
import type { InvestigationState, InvestigationPhase } from '../hooks/useInvestigation'
import type { TurnStatus } from '../../components/turn/turnTypes'
import ProposedCreditCard from '../components/ProposedCreditCard'

interface Props {
  investigation: InvestigationState & { status: TurnStatus | null }
  /** The review the Planner opened, once it exists. */
  review: ReviewController | null
  onStart: () => void
  /** True while the record already shows a credit review, so Investigate is a second run. */
  hasOpenReview: boolean
}

function phaseLabel(phase: InvestigationPhase, hasOpenReview: boolean): string {
  if (phase === 'running') return 'Investigating'
  if (hasOpenReview) return 'Investigate again'
  return 'Investigate'
}

const InvestigationSteps: React.FC<Props> = ({ investigation, review, onStart, hasOpenReview }) => {
  const [builderView] = useBuilderView()
  const { phase, steps, answer, status, error } = investigation
  const live = phase === 'running'

  return (
    <section className="op-investigation" aria-labelledby="op-investigation-title" data-phase={phase} data-testid="operator-investigation">
      <div className="op-investigation-head">
        <div>
          <p className="op-eyebrow">Investigation</p>
          <h2 id="op-investigation-title" className="op-h2">Investigator, then Planner</h2>
        </div>
        <button
          type="button"
          className="op-button"
          onClick={onStart}
          disabled={live}
          data-testid="operator-investigate"
        >
          {phaseLabel(phase, hasOpenReview)}
        </button>
      </div>

      {phase === 'idle' ? (
        <p className="op-note">
          The Investigator reads the orders, the ticket and the return policy with the store tools.
          The Planner proposes one store credit and opens one review. Then it stops.
        </p>
      ) : null}

      {status ? <StatusLine label={status.label} state={status.state} className="op-status" /> : null}
      <StepList steps={steps} live={live} builderView={builderView} folded={phase === 'done'} summary={`How the desk investigated, ${steps.length} ${steps.length === 1 ? 'step' : 'steps'}`} />

      {answer && (answer.investigation.facts.length > 0 || answer.investigation.missing.length > 0) ? (
        <div className="op-brief" data-testid="operator-brief">
          <p className="op-eyebrow">What the records show</p>
          <ul>
            {answer.investigation.facts.map(fact => <li key={fact}>{fact}</li>)}
          </ul>
          {answer.investigation.missing.length > 0 ? (
            <>
              <p className="op-eyebrow">What is missing</p>
              <ul>
                {answer.investigation.missing.map(gap => <li key={gap}>{gap}</li>)}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}

      {phase === 'failed' ? (
        <p className="op-error" role="status" data-testid="operator-investigation-error">
          The investigation did not complete{error ? ` (${error})` : ''}. Nothing was proposed; try again.
        </p>
      ) : null}

      {review?.detail ? <ProposedCreditCard controller={review} compact /> : null}
    </section>
  )
}

export default InvestigationSteps
