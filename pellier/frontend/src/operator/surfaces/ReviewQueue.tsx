/**
 * Prepared actions waiting on a person.
 *
 * The desk's entry point for work that arrived from the storefront. An operator
 * must be able to find Theo without already knowing to look for him, so this
 * surface leads the book rather than hiding behind a client search.
 *
 * Each card reads as continuity from Pellier, not as a support ticket that
 * appeared from nowhere: the origin line names where it began and when. Raw
 * session and turn identifiers are deliberately absent from the default view —
 * they belong behind the proof link on the action itself.
 */

import React, { useState } from 'react'
import { CircleCheck, CircleDashed, CircleMinus, Clock3, ShieldAlert, ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  type OperatorReview,
  requesterLabel,
  requesterLine,
} from '../../services/operator'
import { useReviewQueue } from '../hooks/useReviewQueue'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState from '../components/OperatorState'

/** Proposed actions in the operator's language, not the tool's. */
const ACTION_LABELS: Record<string, string> = {
  initiate_return: 'Return',
  issue_credit: 'Goodwill credit',
  replace_damaged_item: 'Replacement',
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

/**
 * "2 hours ago" from an ISO timestamp, or null when absent.
 *
 * Relative rather than absolute: an operator triaging a queue cares how long
 * someone has been waiting, not the wall-clock time it landed.
 */
export function relativeTime(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return null
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000)
  if (seconds < 0) return 'just now'
  if (seconds < 90) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} minutes ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return hours === 1 ? 'an hour ago' : `${hours} hours ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

/**
 * What became of a review, in one line.
 *
 * Every row said "<action> proposed, awaiting a person" regardless of state, so the
 * three reviews under "Already decided" — one written return, one Cedar denial, one
 * row-level-security refusal — all claimed to be waiting. The right-hand state chip
 * carries the HUMAN axis only, which is why it read "Confirmed" beside that sentence
 * and nothing contradicted it.
 *
 * The axes come from the API, which resolves them from the stored execution receipt.
 * Nothing is inferred here.
 */
/**
 * Coarse outcome for a queue row, derived from the assurance axes rather than
 * the human state alone. A DENY that never entered the tool and a write that
 * reached Aurora both used to render "Confirmed" and differ only in a small
 * grey sentence; the row now carries the distinction as an attribute the
 * stylesheet and an icon can read.
 */
const OutcomeGlyph: React.FC<{ kind: ReviewOutcomeKind }> = ({ kind }) => {
  const Icon =
    kind === 'executed'
      ? CircleCheck
      : kind === 'refused'
        ? ShieldX
        : kind === 'unavailable'
          ? ShieldAlert
        : kind === 'declined'
          ? CircleMinus
          : kind === 'approved'
            ? CircleDashed
            : Clock3
  return <Icon className="operator-review-outcome-glyph" aria-hidden />
}

export type ReviewOutcomeKind =
  | 'pending'
  | 'declined'
  | 'approved'
  | 'refused'
  | 'unavailable'
  | 'executed'
  | 'unknown'

/**
 * The service refused to submit an ungoverned write. The rail is `refused` and
 * the axes say the policy engine was never consulted and Aurora never reached.
 * Nothing ran, which is a different fact from "the outcome was not recorded".
 */
function railRefused(review: OperatorReview): boolean {
  if (review.execution?.rail === 'refused') return true
  const { policy, aurora } = review.assurance
  return policy === 'EVALUATION_INCOMPLETE' && aurora === 'NOT_REACHED'
}

export function outcomeKind(review: OperatorReview): ReviewOutcomeKind {
  if (review.humanState === 'confirmation_required') return 'pending'
  if (review.humanState === 'declined') return 'declined'
  if (!review.execution) return review.executionTurnId ? 'unknown' : 'approved'
  const { policy, aurora, evidence } = review.assurance
  if (aurora === 'PERMITTED' && evidence === 'RECEIPTED') return 'executed'
  if (policy === 'DENY' || aurora === 'DENIED') return 'refused'
  if (railRefused(review)) return 'unavailable'
  return 'unknown'
}

export function outcomeLine(review: OperatorReview): string {
  const action = actionLabel(review.action)
  if (review.humanState === 'confirmation_required') {
    return `${action} proposed, awaiting a person`
  }
  if (review.humanState === 'declined') {
    return `${action} declined. Nothing was submitted.`
  }
  // Confirmed. What happened next depends on whether it was carried out at all.
  if (!review.execution) {
    return review.executionTurnId ? `${action} requested; outcome not yet recorded` : `${action} approved, not yet carried out`
  }
  const { policy, aurora, evidence } = review.assurance
  if (aurora === 'PERMITTED' && evidence === 'RECEIPTED') {
    return policy === 'WOULD_DENY' ? `${action} carried out; policy warning observed with enforcement off` : `${action} carried out`
  }
  if (aurora === 'DENIED') {
    return policy === 'ALLOW' ? `${action} permitted, then refused by Aurora`
      : `${action} refused by Aurora${policy === 'WOULD_DENY' ? '; policy warning observed with enforcement off' : ''}`
  }
  if (policy === 'DENY') return `${action} refused by AgentCore Policy`
  if (railRefused(review)) {
    return `${action} not submitted; the governed rail was unavailable`
  }
  if (policy === 'WOULD_DENY') {
    return `${action} attempted; policy warning observed with enforcement off`
  }
  if (policy === 'EVALUATION_INCOMPLETE') {
    return `${action} attempted; the policy decision could not be read`
  }
  if (policy === 'POLICY_INFERRED') {
    return `${action} attempted; policy text was matched, not evaluated`
  }
  return `${action} attempted; the outcome was not recorded`
}

const ReviewCard: React.FC<{ review: OperatorReview }> = ({ review }) => {
  const when = relativeTime(review.requestedAt)
  const humanState =
    review.humanState === 'confirmation_required'
      ? 'Confirmation required'
      : review.humanState === 'confirmed'
        ? 'Confirmed'
        : 'Declined'
  const HumanIcon = review.humanState === 'confirmed' ? CircleCheck
    : review.humanState === 'declined' ? CircleMinus : Clock3

  return (
    <Link
      to={`/operator/reviews/${review.reviewId}`}
      className="operator-review-row"
      data-testid={`operator-review-${review.reviewId}`}
      data-human-state={review.humanState}
    >
      <ClientAvatar
        customerId={review.customerId}
        name={review.customerName}
        personaId={review.personaId}
      />
      <span className="operator-review-body">
        <span className="operator-client-name">{review.customerName}</span>
        <span className="operator-review-origin">
          Review #{review.reviewId}{review.orderId ? `, order #${review.orderId}` : ''}
        </span>
        <span className="operator-cell-note">
          {review.productName || review.issue || 'Action details awaiting inspection'}
        </span>
        <span className="operator-cell-note operator-review-requester"
          data-testid="operator-review-requester-flag"
          data-requester={review.requesterKind}
          title={requesterLine(review)}
        >
          {requesterLabel(review)}
        </span>
        {when ? <span className="operator-cell-note">Prepared {when}</span> : null}
      </span>
      <span className="operator-review-action-cell">
        <span className="operator-review-cell-label">Prepared action</span>
        <span className="operator-review-cell-value">
          {actionLabel(review.action)}
        </span>
        <span
          className="operator-cell-note operator-review-outcome"
          data-testid="operator-review-outcome"
          data-outcome={outcomeKind(review)}
        >
          <OutcomeGlyph kind={outcomeKind(review)} />
          {outcomeLine(review)}
        </span>
      </span>
      <span
        className="operator-review-state"
        data-state={review.humanState}
      >
        <span className="operator-review-cell-label">Human decision</span>
        <span className="operator-review-state-value">
          <HumanIcon className="operator-review-outcome-glyph" aria-hidden />
          {humanState}
        </span>
      </span>
    </Link>
  )
}

const OUTCOME_FILTERS: ReadonlyArray<{ id: ReviewOutcomeKind; label: string }> = [
  { id: 'pending', label: 'Needs decision' },
  { id: 'refused', label: 'Refused' },
  { id: 'unavailable', label: 'Not submitted' },
  { id: 'executed', label: 'Carried out' },
  { id: 'approved', label: 'Approved, not run' },
  { id: 'declined', label: 'Declined' },
  { id: 'unknown', label: 'Outcome unverified' },
]

const ReviewQueue: React.FC = () => {
  const { queue, error, refreshing, updatedAt, refresh } = useReviewQueue()
  const [outcomeFilter, setOutcomeFilter] = useState<ReviewOutcomeKind | null>(null)

  if (error && !queue) {
    const authenticationRequired =
      error === 'authentication_required' || error === 'invalid_credentials'
    const operatorRequired = error === 'operator_group_required'
    const unavailable = error === 'operator_unavailable'
    return (
      <OperatorState
        level={1}
        data-testid="operator-reviews-error"
        surface={authenticationRequired ? 'plate' : 'paper'}
        eyebrow="Action queue"
        headline={
          authenticationRequired
            ? 'Operator sign-in required'
            : operatorRequired
              ? 'Operator access required'
              : unavailable
                ? 'Operator is temporarily unavailable'
                : 'The action queue is unavailable'
        }
        body={
          authenticationRequired ? (
            <>
              Sign in with the workshop operator account to read the action
              queue. No database request was attempted.
            </>
          ) : operatorRequired ? (
            <>
              This signed-in account is not a member of the operator group. No
              database request was attempted.
            </>
          ) : unavailable ? (
            <>
              The governed service could not be reached, so no current action
              queue was returned.
            </>
          ) : (
            <>
              The live database did not return prepared actions. If this is a
              fresh deployment, confirm migration{' '}
              <code>020_operator_review.sql</code> has been applied.
            </>
          )
        }
        reason={unavailable ? undefined : error}
        action={authenticationRequired ? <OperatorSignInAction unlocks="open the action queue" /> : !operatorRequired ? <button type="button" className="operator-button operator-button-inline" onClick={() => void refresh()}>Try again</button> : undefined}
      />
    )
  }

  if (!queue) {
    return (
      <OperatorState
        level={1}
        data-testid="operator-reviews-loading"
        eyebrow="Action queue"
        headline="Reading the action queue from Aurora…"
      />
    )
  }

  const counts = OUTCOME_FILTERS.reduce<Record<ReviewOutcomeKind, number>>(
    (acc, filter) => {
      acc[filter.id] = queue.reviews.filter((r) => outcomeKind(r) === filter.id).length
      return acc
    },
    { pending: 0, declined: 0, approved: 0, refused: 0, unavailable: 0, executed: 0, unknown: 0 },
  )
  const scoped = outcomeFilter
    ? queue.reviews.filter((r) => outcomeKind(r) === outcomeFilter)
    : queue.reviews
  const pending = scoped.filter(
    (r) => r.humanState === 'confirmation_required',
  )
  const decided = scoped.filter(
    (r) => r.humanState !== 'confirmation_required',
  )

  return (
    <div data-testid="operator-reviews">
      <h1 className="operator-title">Actions awaiting decision</h1>
      <p className="operator-lede">
        Pellier stops consequential work here. Decide the exact terms;
        authorization and execution remain separate.
      </p>

      <div className="operator-queue-toolbar">
        <p role="status">{error ? 'Refresh unavailable. Showing the last successful read.' : updatedAt ? `Updated ${updatedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : 'Reading queue…'}</p>
        <button type="button" className="operator-button operator-button-inline" onClick={() => void refresh()} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>
      </div>
      <div
        className="operator-outcome-filters"
        role="group"
        aria-label="Filter by outcome"
        data-testid="operator-outcome-filters"
      >
        {OUTCOME_FILTERS.map((filter) => (
          <button
            key={filter.id}
            type="button"
            className="operator-outcome-filter"
            aria-pressed={outcomeFilter === filter.id}
            data-outcome={filter.id}
            data-testid={`operator-outcome-filter-${filter.id}`}
            onClick={() =>
              setOutcomeFilter((current) => (current === filter.id ? null : filter.id))
            }
          >
            <OutcomeGlyph kind={filter.id} />
            {filter.label}
            <span className="operator-outcome-filter-count">{counts[filter.id]}</span>
          </button>
        ))}
      </div>

      <dl className="operator-queue-summary" aria-label="Action queue summary">
        <div>
          <dt>Needs decision</dt>
          <dd data-tone={counts.pending > 0 ? 'authority' : 'quiet'}>
            {counts.pending}
          </dd>
        </div>
        <div>
          <dt>Decided</dt>
          <dd>{queue.reviews.length - counts.pending}</dd>
        </div>
        <div>
          <dt>Current boundary</dt>
          <dd className="operator-queue-boundary">Human confirmation</dd>
        </div>
      </dl>

      {/* A clean environment starts here: nothing seeds this table, so an empty
          queue is the designed first impression rather than a failure to load.
          Copy states the mechanism instead of instructing the reader, and stays
          clear of the "all caught up" register - there is nothing to be caught
          up on, and a celebration over an empty queue reads as filler. */}
      {outcomeFilter && scoped.length === 0 ? (
        <OperatorState data-testid="operator-reviews-filter-empty" eyebrow="Filtered actions" headline="No actions match this filter" body={`${counts.pending} action${counts.pending === 1 ? '' : 's'} in the full queue need a decision.`} action={<button type="button" className="operator-button operator-button-inline" onClick={() => setOutcomeFilter(null)}>Show all actions</button>} />
      ) : !outcomeFilter && counts.pending === 0 ? (
        <OperatorState
          level={1}
          data-testid="operator-reviews-empty"
          eyebrow="Action queue"
          headline="No actions waiting"
          body="Consequential actions that Pellier prepares but may not take on its own appear here for an operator to confirm. A shopper asking to return a damaged piece is the usual source."
        />
      ) : (
        <div className="operator-action-list" data-testid="operator-review-pending">
          {pending.map((review) => (
            <ReviewCard review={review} key={review.reviewId} />
          ))}
        </div>
      )}

      {decided.length > 0 ? (
        <>
          <div className="operator-section" data-testid="operator-review-decided-head">
            <span className="operator-section-descriptor">Decision history</span>
            <span className="operator-section-count">{decided.length}</span>
          </div>
          <div className="operator-action-list" data-testid="operator-review-decided">
            {decided.map((review) => (
              <ReviewCard review={review} key={review.reviewId} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}

export default ReviewQueue
