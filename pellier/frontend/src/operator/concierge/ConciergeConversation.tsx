/**
 * Session replay. No chat bubbles.
 *
 * An operator request is a compact request block with an uppercase eyebrow; an
 * assistant turn will render native structured artifacts. Nothing is wrapped in a
 * coloured rounded balloon, because this is a case file rather than a messaging app.
 */

import React from 'react'
import { Link } from 'react-router-dom'
import ServiceIdentity from '../../shared/ServiceIdentity'

import ConciergeInvestigation from './ConciergeInvestigation'
import ConciergeEvidence from './ConciergeEvidence'
import ConciergeRecommendations from './ConciergeRecommendations'
import ConciergePriorResolutions from './ConciergePriorResolutions'
import ConciergeProposedActions from './ConciergeProposedAction'
import ShopperHandoffView from '../components/ShopperHandoffView'
import type { ConciergeMessage } from '../../services/operatorConcierge'

const TURN_STATE_COPY: Record<string, { label: string; detail: string }> = {
  incomplete: {
    label: 'Incomplete',
    detail: 'Request saved. Investigation has not started.',
  },
  failed: {
    label: 'Failed',
    detail: 'Investigation could not be completed.',
  },
}

interface Props {
  messages: ConciergeMessage[]
  customerId?: string
  sessionId?: string | null
  nextStep?: React.ReactNode
  onRetry?: (request: string) => void
}

const ConciergeConversation: React.FC<Props> = ({ messages, customerId, sessionId, nextStep, onRetry }) => {
  // Which turns received an answer. The operator message's own `turnState` is
  // written once as `incomplete` and never updated, because history is append-only
  // and editing what was said would be rewriting the transcript. So completion is
  // DERIVED from the paired assistant message rather than read from a stale field —
  // otherwise a finished turn still reads "Investigation has not started."
  const answered = new Set(
    messages.filter((m) => m.role === 'assistant').map((m) => m.turnId),
  )
  const latestAnswer = messages.filter(
    (message) => message.role === 'assistant' && message.turnState === 'complete',
  ).at(-1)
  const latestResponse = messages.filter((message) => message.role === 'assistant').at(-1)

  return (
  <ol className="operator-concierge-thread" data-testid="operator-concierge-thread">
    {messages.map((message) => {
      if (message.role === 'user') {
        const state = answered.has(message.turnId)
          ? undefined
          : TURN_STATE_COPY[message.turnState]
        return (
          <li className="operator-concierge-turn" key={message.messageId}>
            <div className="operator-concierge-request"
                 data-testid="operator-concierge-request">
              <span className="operator-concierge-eyebrow">Operator request</span>
              <p className="operator-concierge-request-body">{message.content}</p>
            </div>
            {state ? (
              <div
                className="operator-concierge-turnstate"
                data-turn-state={message.turnState}
                data-testid="operator-concierge-turnstate"
              >
                <span className="operator-concierge-eyebrow">{state.label}</span>
                <p className="operator-concierge-turnstate-copy">{state.detail}</p>
              </div>
            ) : null}
          </li>
        )
      }

      const artifact = message.artifact ?? {}
      const failed = message.turnState === 'failed'
      const originalRequest = messages.find(
        (request) => request.role === 'user' && request.turnId === message.turnId,
      )
      return (
        <li className="operator-concierge-turn" key={message.messageId} data-role="assistant">
          {message.content ? (
            <div className="operator-concierge-primary"
                 data-workflow={artifact.workflow || 'client_summary'}>
              {/* A draft is labelled; a summary is not. The label is what stops
                  customer-facing copy from reading as something already sent. */}
              {artifact.primaryLabel || failed ? (
                <span className="operator-concierge-eyebrow"
                      data-testid="operator-concierge-primary-label">
                   {failed ? 'Investigation incomplete' : artifact.primaryLabel}
                </span>
              ) : null}
              <p className="operator-concierge-conclusion">{message.content}</p>
              {failed && message === latestResponse && originalRequest && onRetry ? (
                <button
                  type="button"
                  className="operator-concierge-latest"
                  onClick={() => onRetry(originalRequest.content)}
                >
                  Retry this request
                </button>
              ) : null}
              {artifact.primaryNote ? (
                <p className="operator-concierge-primary-note">
                  {artifact.primaryNote}
                </p>
              ) : null}
            </div>
          ) : null}
          {artifact.recommendation?.body ? (
            <section className="operator-concierge-recommendation"
                     data-testid="operator-concierge-recommendation">
              <h3 className="operator-concierge-section-title">Recommended next step</h3>
              <p className="operator-concierge-recommendation-body">
                {artifact.recommendation.body}
              </p>
              {artifact.workflow === 'investigate_resolution' && !artifact.proposedActions?.length ? (
                <p className="operator-concierge-primary-note">
                  This assessment records no human decision. Review preparation,
                  confirmation, and execution are separate steps.
                </p>
              ) : null}
            </section>
          ) : null}
          {artifact.proposedActions?.length ? (
            <ConciergeProposedActions actions={artifact.proposedActions} />
          ) : null}
          {message === latestAnswer ? nextStep : null}
          {/* Products come before the sections: an operator asked for options, so
              the options lead and the comparison prose follows them. */}
          {artifact.replacement ? (
            <ConciergeRecommendations replacement={artifact.replacement} />
          ) : null}
          {artifact.sections?.length
            ? artifact.sections.map((section) => (
                <section
                  className="operator-concierge-section"
                  key={section.id}
                  data-tone={section.tone}
                  data-testid={`operator-concierge-section-${section.id}`}
                >
                  <span className="operator-concierge-eyebrow">{section.label}</span>
                  <p className="operator-concierge-section-body">{section.body}</p>
                </section>
              ))
            : null}
          {/* Before the evidence list and after the prose: the operator asked what
              happened before, so the answer to that question sits with the answer to
              the one they typed, not buried under the raw evidence rows. */}
          {artifact.priorResolutions ? (
            <ConciergePriorResolutions prior={artifact.priorResolutions} />
          ) : null}
          {artifact.shopperHandoff ? (
            <ShopperHandoffView handoff={artifact.shopperHandoff} compact />
          ) : null}
          {artifact.investigation?.length ? (
            <ConciergeInvestigation
              steps={artifact.investigation}
              orchestration={artifact.orchestration}
            />
          ) : null}
          {artifact.evidence?.length ? (
            <ConciergeEvidence items={artifact.evidence} customerId={customerId} />
          ) : null}
          {artifact.sources?.length ? (
            <section className="operator-concierge-sources"
                     data-testid="operator-concierge-sources">
              <span className="operator-concierge-eyebrow">Evidence sources</span>
              <ul className="operator-concierge-source-list">
                {artifact.sources.map((s) => (
                  <li key={s.source}>
                    <ServiceIdentity source={s.source} />
                    <span className="operator-concierge-source-detail">{s.detail}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {customerId && sessionId && message.turnId ? (
            <div className="operator-concierge-evidence-link">
              <Link
                className="pellier-action-quiet"
                to={`/observatory/operator-turn?${new URLSearchParams({
                  customer: customerId, session: sessionId, turn: message.turnId,
                })}`}
              >
                Inspect this turn in Observatory
              </Link>
            </div>
          ) : null}
        </li>
      )
    })}
  </ol>
  )
}

export default ConciergeConversation
