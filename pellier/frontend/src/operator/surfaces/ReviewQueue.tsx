/**
 * The reviews: every proposed credit waiting on a person, and the decided ones,
 * with the clients' store credit requests listed beneath them.
 *
 * The desk's rail when a review is open. Each row names the client, the
 * amount and one word for where the credit stands. The word carries the
 * meaning; the tag's color repeats it. A request has no amount and no
 * decision: its row leads to the client record, where Investigate answers it.
 */
import React from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { StatusTag, type TagTone } from '../../components/turn'
import { useReviewQueue } from '../hooks/useReviewQueue'
import type { OperatorCreditRequest, OperatorReview } from '../../services/operator'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState, { describeOperatorError } from '../components/OperatorState'

export interface ReviewOutcome {
  tone: TagTone
  word: string
  pulse: boolean
}

/** Where a credit stands, from the axes the API resolved. Nothing is inferred. */
export function reviewOutcome(review: OperatorReview): ReviewOutcome {
  if (review.humanState === 'confirmation_required') return { tone: 'pending', word: 'Waiting for Nadia', pulse: true }
  if (review.humanState === 'declined') return { tone: 'blocked', word: 'Declined', pulse: false }
  const { policy, aurora, evidence } = review.assurance
  if (aurora === 'PERMITTED' && evidence === 'RECEIPTED') return { tone: 'good', word: 'Credited', pulse: false }
  if (policy === 'DENY') return { tone: 'blocked', word: 'DENY', pulse: false }
  if (aurora === 'DENIED') return { tone: 'blocked', word: 'Refused by Aurora', pulse: false }
  // An attempt that left no credit and no audit row: refused, failed, or with
  // no answer stored. The list says what the tables say.
  if (evidence === 'NO_EXECUTION') return { tone: 'blocked', word: 'Not written', pulse: false }
  if (review.execution || review.executionTurnId) return { tone: 'pending', word: 'Outcome unverified', pulse: false }
  // The Lab 4 check confirms its own probe; no person approved it.
  if (review.policyCheckProbe) return { tone: 'pending', word: 'Lab 4 probe', pulse: false }
  return { tone: 'good', word: 'Approved', pulse: false }
}

const ReviewRow: React.FC<{ review: OperatorReview; selected: boolean }> = ({ review, selected }) => {
  const outcome = reviewOutcome(review)
  return (
    <li>
      <NavLink
        to={`/operator/reviews/${review.reviewId}`}
        className="op-row"
        aria-current={selected ? 'page' : undefined}
        data-testid={`operator-review-${review.reviewId}`}
        data-outcome={outcome.word}
      >
        <ClientAvatar customerId={review.customerId} name={review.customerName} personaId={review.personaId} />
        <span className="op-row-body">
          <span className="op-row-head">
            <span className="op-row-name">{review.customerName}</span>
            <StatusTag tone={outcome.tone} pulse={outcome.pulse}>{outcome.word}</StatusTag>
          </span>
          <span className="op-row-line">${review.amount} store credit</span>
          <span className="op-row-sub">{review.reason}</span>
        </span>
      </NavLink>
    </li>
  )
}

/** What a request's tag says: open until an investigation answers it. */
export function requestOutcome(request: OperatorCreditRequest): ReviewOutcome {
  return request.status === 'open'
    ? { tone: 'pending', word: 'Open request', pulse: false }
    : { tone: 'good', word: 'Investigated', pulse: false }
}

const RequestRow: React.FC<{ request: OperatorCreditRequest }> = ({ request }) => {
  const outcome = requestOutcome(request)
  return (
    <li>
      <Link
        to={`/operator/clients/${encodeURIComponent(request.customerId)}`}
        className="op-row"
        data-testid={`operator-request-${request.requestId}`}
        data-outcome={outcome.word}
      >
        <ClientAvatar customerId={request.customerId} name={request.customerName} personaId={request.personaId} />
        <span className="op-row-body">
          <span className="op-row-head">
            <span className="op-row-name">{request.customerName}</span>
            <StatusTag tone={outcome.tone} pulse={outcome.pulse}>{outcome.word}</StatusTag>
          </span>
          <span className="op-row-line">Store credit request, no amount</span>
          {request.issue ? <span className="op-row-sub">{request.issue}</span> : null}
        </span>
      </Link>
    </li>
  )
}

/** The list, as the desk's rail. */
export const ReviewList: React.FC = () => {
  const { queue, error, refresh } = useReviewQueue()
  const { reviewId = '' } = useParams()

  if (error && !queue) {
    const described = describeOperatorError(error, 'read the reviews')
    return (
      <OperatorState
        level={2}
        data-testid="operator-reviews-error"
        eyebrow="Reviews"
        headline={described.headline}
        body={described.body}
        reason={error === 'operator_unavailable' ? undefined : error}
        action={described.signIn
          ? <OperatorSignInAction unlocks="read the reviews" />
          : error !== 'operator_group_required'
            ? <button type="button" className="op-button op-button-quiet" onClick={() => void refresh()}>Try again</button>
            : undefined}
      />
    )
  }
  if (!queue) {
    return <OperatorState level={2} data-testid="operator-reviews-loading" eyebrow="Reviews" headline="Reading the reviews" busy />
  }
  return (
    <nav className="op-list" aria-label="Reviews" data-testid="operator-reviews">
      <div className="op-list-head">
        <h2 className="op-h2">Reviews</h2>
        <span className="op-list-count" data-testid="operator-reviews-count">
          {queue.pendingCount === 1 ? '1 waiting' : `${queue.pendingCount} waiting`}
        </span>
      </div>
      {queue.total === 0 ? (
        <p className="op-note" data-testid="operator-reviews-empty">
          No credit to approve. A credit the Planner proposes appears here.
        </p>
      ) : (
        <ul>
          {queue.reviews.map(review => (
            <ReviewRow key={review.reviewId} review={review} selected={String(review.reviewId) === reviewId} />
          ))}
        </ul>
      )}
      {queue.requests.length > 0 ? (
        <div className="op-list-group" data-testid="operator-requests">
          <div className="op-list-head">
            <h3 className="op-h3">Requests</h3>
            <span className="op-list-count" data-testid="operator-requests-count">
              {`${queue.openRequestCount} open`}
            </span>
          </div>
          <ul aria-label="Store credit requests">
            {queue.requests.map(request => <RequestRow key={request.requestId} request={request} />)}
          </ul>
        </div>
      ) : null}
    </nav>
  )
}

/** The reviews page: the rail carries the list; the desk waits for a choice. */
const ReviewQueue: React.FC = () => (
  <OperatorState
    level={1}
    data-testid="operator-reviews-choose"
    eyebrow="Reviews"
    headline="Choose a review"
    body="Each review is one proposed store credit. Approving binds to its exact amount, reason and customer; executing asks whether the system may carry it out."
  />
)

export default ReviewQueue
