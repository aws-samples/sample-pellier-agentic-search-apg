import type { ConciergeInvestigationStep, ConciergeStreamAnswer } from '../../services/operatorConcierge'
import ResolutionTrace from '../../shared/trace/ResolutionTrace'
import { operatorTraceSteps } from './traceSteps'

interface Props {
  request: string
  steps: ConciergeInvestigationStep[]
  answer: ConciergeStreamAnswer | null
}

export default function ConciergePendingTurn({ request, steps, answer }: Props) {
  return (
    <li className="operator-concierge-turn" data-testid="operator-concierge-pending">
      <div className="operator-concierge-request">
        <span className="operator-concierge-eyebrow">You</span>
        <p className="operator-concierge-request-body">{request}</p>
      </div>
      <div data-testid="operator-concierge-live-activity">
        <ResolutionTrace title="How this answer is being built" mode="live" compact
          steps={operatorTraceSteps(steps)} busy={!answer}
          outcome={answer ? {
            label: answer.status === 'failed' ? 'Investigation did not complete' : 'Answer saved to the conversation',
            status: answer.status === 'failed' ? 'failed' : 'complete',
            body: 'Any proposed action still follows its separate review and approval controls.',
          } : null}
        />
      </div>
      {answer && (
        <div className="operator-concierge-primary operator-concierge-primary--live" data-testid="operator-concierge-live-answer">
          {answer.primaryLabel && <span className="operator-concierge-eyebrow">{answer.primaryLabel}</span>}
          <p className="operator-concierge-conclusion">{answer.summary}</p>
        </div>
      )}
    </li>
  )
}
