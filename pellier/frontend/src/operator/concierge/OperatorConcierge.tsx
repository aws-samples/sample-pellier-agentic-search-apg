/**
 * The advisor's workbench beside the client record.
 *
 * Not a chat widget. Operator requests are compact editorial blocks, not bubbles;
 * assistant output will be native structured artifacts, not one assistant balloon.
 * The visual weight sits in typography and whitespace rather than nested cards,
 * which is what keeps a pane full of governance machinery feeling calm.
 *
 * Nothing here fabricates. When orchestration is absent the surface says so; when a
 * governed action is closed it says which and why. A composer that visibly accepts a
 * question it cannot answer is worse than no composer, so it is gated.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { OperatorClientRecord } from '../../services/operator'

import ServiceSource from '../components/ServiceSource'
import ServiceLogo from '../components/ServiceLogo'
import ConciergeCapabilityState from './ConciergeCapabilityState'
import ConciergeHumanCheckpoint from './ConciergeHumanCheckpoint'
import ConciergePendingTurn from './ConciergePendingTurn'
import ConciergeSuggestions from './ConciergeSuggestions'
import {
  GUIDED_SERVICE_RECOVERY_PROMPTS,
  TEMPLATES,
  buildTemplateContext,
} from './templates'
import ConciergeComposer from './ConciergeComposer'
import ConciergeConversation from './ConciergeConversation'
import ConciergeEmptyState from './ConciergeEmptyState'
import { useOperatorConcierge } from './useOperatorConcierge'
import { conversationReviewHref } from './conversationLinks'
import { useOperatorQueueRefresh } from '../shell/OperatorFrame'
import { useReviewQueue } from '../hooks/useReviewQueue'

interface Props {
  clientId: string
  clientName: string
  membershipLabel: string
  spendLabel: string
  /** Loaded record state, so suggestions derive from real context. */
  record: OperatorClientRecord | null
  /** Starts the canonical Jessica case as a fresh, observable run. */
  guidedServiceRecovery?: boolean
  initialSessionId?: string | null
  initialTurnId?: string | null
}

const OperatorConcierge: React.FC<Props> = ({
  clientId,
  clientName,
  membershipLabel,
  spendLabel,
  record,
  guidedServiceRecovery = false,
  initialSessionId,
  initialTurnId,
}) => {
  const concierge = useOperatorConcierge(clientId, {
    resumeLatest: !guidedServiceRecovery,
    initialSessionId,
  })
  const refreshQueue = useOperatorQueueRefresh()
  const { queue } = useReviewQueue()
  const hasConversation = concierge.messages.length > 0
  const inFlight = concierge.pendingRequest !== null
  // Deterministic, from loaded state. No model decides what to suggest.
  const templateContext = useMemo(() => buildTemplateContext(record), [record])
  const guidedStarted = useRef(false)
  const hasAnsweredTurn = concierge.messages.some(
    (message) => message.role === 'assistant' && message.turnState === 'complete',
  )
  const hasPreparedAction = concierge.messages.some(
    (message) => message.artifact?.proposedActions?.some(
      (action) => action.reviewId != null,
    ),
  )
  // A durable proposal can precede later discussion. Keep its handoff reachable
  // without representing the historical proposal as a current pending decision.
  const preparedTurn = [...concierge.messages].reverse().find(message =>
    message.role === 'assistant' && message.turnState === 'complete' &&
    message.artifact?.proposedActions?.some(action => action.reviewId != null),
  )
  const preparedReviewIds = [...new Set(preparedTurn?.artifact?.proposedActions
    ?.flatMap(action => action.reviewId != null ? [action.reviewId] : []) ?? [])]
  const preparedReviewKey = preparedReviewIds.join(',')
  useEffect(() => {
    if (preparedReviewKey) refreshQueue()
  }, [preparedReviewKey, refreshQueue])
  // A newer discussion may have no proposal of its own. The authenticated
  // queue can still supply the next pending review for this same client.
  const pendingClientReview = queue?.reviews?.find(review =>
    review.customerId === clientId && review.humanState === 'confirmation_required',
  )
  const handoffReviewIds = preparedReviewIds.length ? preparedReviewIds
    : pendingClientReview ? [pendingClientReview.reviewId] : []
  const handoffTurnId = preparedTurn?.turnId ?? [...concierge.messages].reverse().find(
    message => message.role === 'assistant' && message.turnState === 'complete',
  )?.turnId
  const guidedCompletedTurns = useMemo(() => {
    if (!guidedServiceRecovery) return 0
    const answeredTurns = new Set(concierge.messages.filter(
      (message) => message.role === 'assistant' && message.turnState === 'complete',
    ).map((message) => message.turnId))
    let completed = 0
    for (const prompt of GUIDED_SERVICE_RECOVERY_PROMPTS) {
      const answered = concierge.messages.some(
        (message) =>
          message.role === 'user' &&
          message.content === prompt &&
          answeredTurns.has(message.turnId),
      )
      if (!answered) break
      completed += 1
    }
    return completed
  }, [concierge.messages, guidedServiceRecovery])
  const nextGuidedPrompt =
    guidedServiceRecovery && guidedCompletedTurns > 0
      ? GUIDED_SERVICE_RECOVERY_PROMPTS[guidedCompletedTurns]
      : undefined
  const nextGuidedLabel =
    guidedCompletedTurns === 1
      ? 'Check the source records'
      : 'Get the final recommendation'

  useEffect(() => {
    if (
      !guidedServiceRecovery ||
      guidedStarted.current ||
      !concierge.composerEnabled ||
      concierge.status === 'loading' ||
      concierge.status === 'submitting' ||
      !templateContext
    ) {
      return
    }
    const template = TEMPLATES.find(
      (candidate) => candidate.id === 'investigate_resolution',
    )
    if (
      !template ||
      !concierge.config?.supportedWorkflowKinds?.includes(template.workflow)
    ) {
      return
    }
    guidedStarted.current = true
    void concierge.submit(GUIDED_SERVICE_RECOVERY_PROMPTS[0])
  }, [
    concierge.composerEnabled,
    concierge.config?.supportedWorkflowKinds,
    concierge.status,
    concierge.submit,
    guidedServiceRecovery,
    templateContext,
  ])

  const body = useRef<HTMLDivElement | null>(null)
  const following = useRef(true)
  const revealedTurn = useRef<string | null>(null)
  const [showLatest, setShowLatest] = useState(false)
  const goToLatest = () => {
    const el = body.current
    if (!el) return
    const turns = el.querySelectorAll(
      inFlight ? '.operator-concierge-request' : '[data-role="assistant"]',
    )
    const newest = turns[turns.length - 1]
    if (newest) el.scrollTop += newest.getBoundingClientRect().top - el.getBoundingClientRect().top
    following.current = true
    setShowLatest(false)
  }
  useEffect(() => {
    const targetKey = `${concierge.sessionId}/${initialTurnId}`
    if (initialTurnId && !inFlight && revealedTurn.current !== targetKey) {
      const el = body.current
      const target = [...(el?.querySelectorAll<HTMLElement>('[data-turn-id]') ?? [])]
        .find(node => node.dataset.turnId === initialTurnId)
      if (el && target) {
        el.scrollTop += target.getBoundingClientRect().top - el.getBoundingClientRect().top
        target.focus({ preventScroll: true })
        revealedTurn.current = targetKey
        following.current = false
        setShowLatest(target !== el.querySelector('[data-role="assistant"]:last-child'))
        return
      }
    }
    if (following.current) goToLatest()
    else setShowLatest(true)
  }, [concierge.messages, concierge.pendingRequest, concierge.liveAnswer, concierge.sessionId, initialTurnId, inFlight])

  const nextStep = !inFlight ? (
    <>
      {nextGuidedPrompt ? (
        <section
          className="operator-concierge-guided-next"
          data-testid="operator-concierge-guided-next"
          aria-label={`Guided Jessica case, turn ${guidedCompletedTurns + 1} of ${GUIDED_SERVICE_RECOVERY_PROMPTS.length}`}
        >
          <div>
            <span>Optional follow-up {guidedCompletedTurns} of 2</span>
            <p>{nextGuidedPrompt}</p>
            <p className="operator-concierge-primary-note">
              This continues the investigation. It does not prepare or approve a return.
            </p>
          </div>
          <button
            type="button"
            disabled={!concierge.composerEnabled}
            onClick={() => void concierge.submit(nextGuidedPrompt)}
          >
            {nextGuidedLabel}
          </button>
        </section>
      ) : null}
      {hasAnsweredTurn &&
      !hasPreparedAction &&
      (!guidedServiceRecovery ||
        guidedCompletedTurns === GUIDED_SERVICE_RECOVERY_PROMPTS.length) &&
      record?.client.returnEvidence?.unconfirmedReturnAssertion ? (
        <ConciergeHumanCheckpoint
          record={record}
          disabled={!concierge.composerEnabled}
          onPrepare={(request) => void concierge.submit(request)}
        />
      ) : null}
    </>
  ) : null
  const hasNextStep = !inFlight && (
    Boolean(nextGuidedPrompt) ||
    (hasAnsweredTurn && !hasPreparedAction &&
      (!guidedServiceRecovery || guidedCompletedTurns === GUIDED_SERVICE_RECOVERY_PROMPTS.length) &&
      record?.client.returnEvidence?.unconfirmedReturnAssertion)
  )
  const focusNextStep = () => {
    const el = body.current
    const target = el?.querySelector<HTMLElement>(
      '[data-testid="operator-concierge-human-checkpoint"], [data-testid="operator-concierge-guided-next"]',
    )
    if (!el || !target) return
    el.scrollTop += target.getBoundingClientRect().top - el.getBoundingClientRect().top
    target.querySelector<HTMLElement>('input, button')?.focus()
  }

  return (
    <section
      className="operator-concierge"
      id="operator-concierge"
      aria-labelledby="operator-concierge-title"
      data-testid="operator-concierge"
    >
      <header className="operator-concierge-head">
        <div className="operator-concierge-heading-row">
        <h2 className="operator-concierge-title" id="operator-concierge-title">
          Operator Concierge
        </h2>
        <a href="#operator-client-record" className="operator-concierge-record-link">Client record</a>
        </div>
        {/*
          * Orientation, and only until it is no longer needed.
          *
          * Both of these sat above the scroller for the life of the pane, so
          * roughly seventy pixels of a viewport-height column explained what
          * the Concierge is while an operator was trying to read what it
          * found. The evidence block below could then show two lines at a
          * time. They earn their place on arrival and yield once there is a
          * conversation to read. An in-flight turn counts: the request is on
          * screen and its steps are arriving, so the orientation copy was
          * holding 110px of a 175px reading area to explain a pane the
          * operator is already using.
          */}
        {hasConversation || inFlight ? null : (
          <>
            <p className="operator-concierge-sub">
              Grounded in this client&rsquo;s orders, preferences, inventory, returns,
              and governed actions from{' '}
              {concierge.config?.dataSource ?? 'the live database'}.
            </p>
            <div
              className="operator-concierge-path"
              aria-label="Strands Graph path: Case Investigator, then Resolution Planner"
            >
              <span className="operator-concierge-path-label">
                <ServiceLogo service="strands" size={20} />
                Strands Graph
              </span>
              <span>Case Investigator</span>
              <ArrowRight size={13} strokeWidth={1.8} aria-hidden="true" />
              <span>Resolution Planner</span>
            </div>
          </>
        )}
        {/* Scope, not a second profile: enough to make the conversation's subject
            unambiguous without repeating the record on the left. */}
        <p className="operator-concierge-scope" data-testid="operator-concierge-scope">
          <span className="operator-concierge-scope-name">{clientName}</span>
          <span className="operator-concierge-scope-meta">
            {membershipLabel}, {spendLabel}
          </span>
        </p>
      </header>

      <div className="operator-concierge-service"><ServiceSource service="agentcore">Governed tool access and policy</ServiceSource></div>
      <ConciergeCapabilityState
        status={concierge.status}
        capabilities={concierge.capabilities}
        config={concierge.config}
      />

      <div
        className="operator-concierge-body"
        data-testid="operator-concierge-body"
        ref={body}
        onScroll={(event) => {
          // Marks the scroller so the stylesheet fades its top edge only once
          // something has actually scrolled past it.
          const el = event.currentTarget
          el.dataset.scrolled = el.scrollTop > 4 ? 'true' : 'false'
          following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100
          if (following.current) setShowLatest(false)
        }}
      >
        {hasConversation || inFlight ? (
          <>
            <ConciergeConversation
              messages={concierge.messages}
              customerId={clientId}
              sessionId={concierge.sessionId}
              nextStep={nextStep}
              onRetry={!inFlight && concierge.composerEnabled
                ? (request) => void concierge.submit(request) : undefined}
            />
            {inFlight ? (
              <ol className="operator-concierge-thread">
                <ConciergePendingTurn
                  request={concierge.pendingRequest ?? ''}
                  steps={concierge.liveSteps}
                  answer={concierge.liveAnswer}
                />
              </ol>
            ) : null}
          </>
        ) : (
          <>
            <ConciergeEmptyState loading={concierge.status === 'loading'} />
            {/* Not while loading. A stored thread has not arrived yet, so offering
                actions here would flash four rows and then replace them with the
                conversation they were never relevant to. */}
            {concierge.composerEnabled && concierge.status !== 'loading' ? (
              <ConciergeSuggestions
                context={templateContext}
                supportedWorkflows={concierge.config?.supportedWorkflowKinds}
                disabled={inFlight}
                onSelect={(template) => {
                  if (!templateContext) return
                  // A template is a shortcut into the SAME orchestrator: it builds a
                  // request and submits it. No separate endpoint, no canned answer.
                  void concierge.submit(template.buildRequest(templateContext))
                }}
              />
            ) : null}
          </>
        )}
      </div>

      {!inFlight && handoffReviewIds.length ? (
        <nav className="operator-concierge-review-handoff" aria-label="Prepared reviews" data-testid="operator-concierge-review-handoff">
          <p>{preparedReviewIds.length
            ? 'Prepared in this conversation. Review the exact terms and current outcome.'
            : `A prepared action for ${clientName} is awaiting human review.`}</p>
          <div>{handoffReviewIds.map(reviewId => (
            <Link key={reviewId} to={conversationReviewHref(reviewId, concierge.sessionId, handoffTurnId, clientId)}>
              Open review #{reviewId}
            </Link>
          ))}</div>
        </nav>
      ) : null}
      {hasNextStep || showLatest ? (
        <nav className="operator-concierge-navigation" aria-label="Conversation navigation">
          {showLatest ? <button type="button" className="operator-concierge-latest" onClick={goToLatest}>Latest reply</button> : null}
          {hasNextStep ? (
            <button type="button" className="operator-concierge-latest" onClick={focusNextStep}>
              {nextGuidedPrompt ? 'View optional follow-up' : 'Choose return details'}
            </button>
          ) : null}
        </nav>
      ) : null}
      {concierge.status === 'conversation_unavailable' || concierge.status === 'config_unavailable' ? (
        <div className="operator-concierge-recovery" role="status">
          <p>{concierge.error || (concierge.status === 'config_unavailable' ? 'The investigation service configuration could not be read.' : 'Saved conversation history could not be verified.')}</p>
          <button type="button" onClick={() => void concierge.retryHistory()}>Retry history</button>
          {concierge.config?.composerEnabled ? <button type="button" onClick={concierge.startNew}>Start a new conversation</button> : null}
        </div>
      ) : null}
      {concierge.status === 'submitting' ? <div className="operator-concierge-recovery"><button type="button" onClick={concierge.stopReceiving}>Stop receiving</button><p>Stops updates here. The server may continue; refresh history before retrying.</p></div> : null}
      <ConciergeComposer
        loading={concierge.status === 'loading'}
        enabled={concierge.composerEnabled}
        submitting={concierge.status === 'submitting'}
        note={concierge.config?.note ?? ''}
        error={concierge.error}
        onSubmit={concierge.submit}
      />
    </section>
  )
}

export default OperatorConcierge
