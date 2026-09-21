/**
 * A prepared action, waiting for a person.
 *
 * The whole design problem here is one sentence: preparing is not authorizing, and
 * confirming is not executing. So this component states three things separately and
 * never lets one imply another —
 *
 *   what was prepared        the exact parameters a human will be bound to
 *   human confirmation       required, or the decision that was recorded
 *   governed execution       whether the rail can run it at all, right now
 *
 * The four assurance axes come from the review API and are rendered by the existing
 * `ActionAssurance` component, unchanged. There is no confirm control here: the
 * canonical human decision lives on the ReviewRecord surface, and duplicating that
 * form would create two implementations of the one thing that must not drift.
 *
 * Historical artifact versus current state: the artifact says what was PROPOSED at
 * the time, which is immutable. What the human has since decided is read live from
 * the review API, because a transcript is history and a decision is current.
 */

import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import ActionAssurance from '../components/ActionAssurance'
import { fetchReview } from '../../services/operator'
import type { OperatorReviewDetail } from '../../services/operator'
import type { ConciergeProposedAction } from '../../services/operatorConcierge'
import { conversationReviewHref } from './conversationLinks'

const EXECUTION_COPY: Record<string, string> = {
  available: 'Available',
  review_required: 'Requires human confirmation',
  temporarily_unavailable: 'Temporarily unavailable',
  not_enabled: 'Not enabled',
  capability_state_unverified: 'Could not be confirmed',
}

const HUMAN_COPY: Record<string, string> = {
  confirmation_required: 'Required',
  confirmed: 'Confirmed',
  declined: 'Declined',
}

const STATE_NOTE: Record<string, string> = {
  review_already_open: 'This exact action was already awaiting a decision.',
  not_enabled: 'No review was prepared, because this capability is not published.',
  could_not_prepare_review: 'No review is awaiting a decision.',
}

function money(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function reasonLabel(reason: string): string {
  return reason.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

interface Props {
  action: ConciergeProposedAction
  customerId?: string
  sessionId?: string | null
  turnId?: string | null
}

const ConciergeProposedActionCard: React.FC<Props> = ({ action, customerId, sessionId, turnId }) => {
  const [review, setReview] = useState<OperatorReviewDetail | null>(null)
  const [readState, setReadState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const reviewId = action.reviewId ?? null

  useEffect(() => {
    if (reviewId === null) {
      setReview(null)
      return
    }
    let active = true
    setReview(null)
    setReadState('loading')
    // Current state, not the artifact's. A confirmation recorded ten minutes after
    // this turn must show here, and the transcript must not be rewritten to say so.
    void fetchReview(reviewId)
      .then((detail) => {
        if (active) {
          setReview(detail)
          setReadState('ready')
        }
      })
      .catch(() => {
        if (active) {
          setReview(null)
          setReadState('failed')
        }
      })
    return () => {
      active = false
    }
  }, [reviewId])

  const execution = action.executionCapability?.state ?? 'capability_state_unverified'
  const humanState = review?.review.humanState

  return (
    <section
      className="operator-concierge-proposal"
      data-state={action.state}
      data-execution={execution}
      data-testid="operator-concierge-proposal"
    >
      <h3 className="operator-concierge-proposal-title">
        {reviewId !== null
          ? action.tool === 'initiate_return' ? 'Return review prepared' : 'Action review prepared'
          : 'Review not prepared'}
      </h3>

      <dl className="operator-concierge-proposal-rows">
        {action.product?.name ? (
          <div>
            <dt>Item</dt>
            <dd>
              {action.product.name}
              {typeof action.product.price === 'number'
                ? `, ${money(action.product.price)}`
                : ''}
            </dd>
          </div>
        ) : null}
        {action.order?.orderId ? (
          <div>
            <dt>Order</dt>
            <dd>#{action.order.orderId}</dd>
          </div>
        ) : null}
        {action.material?.reason ? (
          <div>
            <dt>Reason</dt>
            <dd>{reasonLabel(action.material.reason)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Human confirmation</dt>
          <dd data-testid="operator-concierge-proposal-human">
            {reviewId === null ? 'No review prepared' : humanState
              ? HUMAN_COPY[humanState] ?? humanState
              : readState === 'failed' ? 'Could not read current decision' : 'Reading current decision…'}
          </dd>
        </div>
        <div>
          {/* Separate row, separate fact. A confirmed review does not make a closed
              rail open, and a closed rail does not invalidate the decision. */}
          <dt>Execution availability when prepared</dt>
          <dd data-testid="operator-concierge-proposal-execution">
            {EXECUTION_COPY[execution] ?? execution}
          </dd>
        </div>
      </dl>

      {STATE_NOTE[action.state] || action.note ? (
        <p className="operator-concierge-proposal-note">
          {STATE_NOTE[action.state] ?? action.note}
        </p>
      ) : null}

      {review ? (
        <div className="operator-concierge-proposal-assurance">
          {/* The existing four-axis component, verbatim. A second implementation is
              how two surfaces start disagreeing about what "governed" means. */}
          <ActionAssurance assurance={review.review.assurance} />
        </div>
      ) : null}

      {reviewId !== null ? (
        <>
          <p className="operator-concierge-proposal-note">
            Review #{reviewId} is saved in Action Queue.{' '}
            {humanState === 'confirmation_required'
              ? 'Open it to confirm or decline these terms. Execution is a separate step.'
              : 'Open it to read the current decision and execution evidence.'}
          </p>
          <Link
            className="operator-concierge-proposal-link"
            to={conversationReviewHref(reviewId, sessionId, turnId, customerId)}
            data-testid="operator-concierge-proposal-review-link"
          >
            {humanState === 'confirmation_required' ? action.tool === 'initiate_return' ? 'Review this return' : 'Review this action'
              : humanState ? 'View review outcome' : `Open review #${reviewId}`}
          </Link>
        </>
      ) : null}
    </section>
  )
}

interface ListProps {
  actions: ConciergeProposedAction[]
  customerId?: string
  sessionId?: string | null
  turnId?: string | null
}

const ConciergeProposedActions: React.FC<ListProps> = ({ actions, customerId, sessionId, turnId }) => {
  if (!actions.length) return null
  return (
    <>
      {/* One consequential action, one review. Never an "approve plan" over several. */}
      {actions.map((action) => (
        <ConciergeProposedActionCard
          action={action}
          customerId={customerId}
          sessionId={sessionId}
          turnId={turnId}
          key={`${action.tool}-${action.reviewId ?? action.state}`}
        />
      ))}
    </>
  )
}

export default ConciergeProposedActions
