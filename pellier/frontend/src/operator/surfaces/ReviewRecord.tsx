/**
 * One review: the proposed credit, its three checks, and the decision.
 *
 * Reading order is the person's reasoning order: who the client is, what the
 * credit covers, what the Planner said, then the card with Approve and
 * Decline, then Execute once approved. Everything factual is hydrated by the
 * API from the table that owns it.
 */
import React from 'react'
import { Link, useParams } from 'react-router-dom'
import { StatusTag } from '../../components/turn'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState, { describeOperatorError } from '../components/OperatorState'
import ProposedCreditCard from '../components/ProposedCreditCard'
import { useReview } from '../hooks/useReview'
import { shortDate } from './ClientBook'
import { reviewOutcome } from './ReviewQueue'

const ReviewRecordPage: React.FC = () => {
  const { reviewId } = useParams<{ reviewId: string }>()
  const numericId = Number(reviewId)
  const controller = useReview(Number.isFinite(numericId) ? numericId : null)
  const { detail, error } = controller

  if (error || (reviewId && !Number.isFinite(numericId))) {
    const code = error ?? 'review_not_found'
    const described = describeOperatorError(code, 'open this review')
    return (
      <OperatorState
        level={1}
        data-testid="operator-review-error"
        eyebrow="Review"
        headline={code === 'review_not_found' ? 'No such review' : described.headline}
        body={code === 'review_not_found' ? 'The reviews list is the current one.' : described.body}
        reason={code}
        action={described.signIn ? <OperatorSignInAction unlocks="open this review" /> : undefined}
      />
    )
  }
  if (!detail) {
    return <OperatorState level={1} data-testid="operator-review-loading" eyebrow="Review" headline="Reading the review" busy />
  }

  const { review, client, orders } = detail
  const outcome = reviewOutcome(review)
  const items = orders.length > 0 ? orders.map(o => o.productName) : review.recommendation.items ?? []

  return (
    <>
      <article className="op-record" data-testid="operator-review-record" aria-labelledby="op-review-title">
        <header className="op-record-head">
          <ClientAvatar customerId={client.customerId} name={client.name} personaId={client.personaId} size="lg" />
          <div>
            <p className="op-eyebrow">Review {review.reviewId}</p>
            <h1 id="op-review-title" className="op-h1">{client.name}</h1>
            <p className="op-record-meta">
              <StatusTag tone={outcome.tone} pulse={outcome.pulse}>{outcome.word}</StatusTag>
              <Link to={`/operator/clients/${encodeURIComponent(client.customerId)}`} className="op-link" data-testid="operator-review-client-link">
                Open the record
              </Link>
            </p>
          </div>
        </header>

        <section className="op-card" aria-labelledby="op-review-items-title" data-testid="operator-review-items">
          <div className="op-card-head">
            <h2 id="op-review-items-title" className="op-h2">What the credit covers</h2>
          </div>
          {orders.length > 0 ? (
            <table className="op-table">
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col" className="op-col-optional">Placed</th>
                  <th scope="col" className="op-num">Paid</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(order => (
                  <tr key={order.orderId}>
                    <td>
                      <span className="op-item-name">{order.productName}</span>
                      <span className="op-row-sub">{order.brand}, order {order.orderId}</span>
                    </td>
                    <td className="op-col-optional">{shortDate(order.placedAt) ?? ''}</td>
                    <td className="op-num">${order.amountPaid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="op-note">{items.length > 0 ? items.join(' and ') : 'No order was named for this credit.'}</p>
          )}
          <dl className="op-key">
            <div>
              <dt>Asked for by</dt>
              <dd>{review.requesterKind === 'operator' ? 'the Planner, on the desk' : review.requesterKind === 'shopper' ? 'the signed-in shopper' : 'an unverified request'}</dd>
            </div>
            {review.requestedAt ? <div><dt>Proposed</dt><dd>{shortDate(review.requestedAt)}</dd></div> : null}
            {review.decidedAt ? <div><dt>Decided</dt><dd>{shortDate(review.decidedAt)}</dd></div> : null}
          </dl>
        </section>

        {review.execution ? (
          <section className="op-card" aria-labelledby="op-review-receipt-title" data-testid="operator-review-receipt">
            <div className="op-card-head">
              <h2 id="op-review-receipt-title" className="op-h2">What ran</h2>
            </div>
            <dl className="op-key">
              <div><dt>Rail</dt><dd>{review.execution.rail ?? 'no row written'}</dd></div>
              <div><dt>Execution turn</dt><dd>{review.execution.executionTurnId}</dd></div>
              <div><dt>Write key</dt><dd>{review.execution.idempotencyKey}</dd></div>
              {review.execution.lastAttempt ? (
                <div data-testid="operator-review-last-attempt">
                  <dt>Gateway answered the desk</dt>
                  <dd>
                    {review.execution.lastAttempt.outcome}, {shortDate(review.execution.lastAttempt.at)} (stored)
                  </dd>
                </div>
              ) : null}
              {review.execution.lastAttempt?.policyDigest ? (
                <div><dt>Policy set</dt><dd>{review.execution.lastAttempt.policyDigest.slice(0, 19)}</dd></div>
              ) : null}
            </dl>
          </section>
        ) : null}
      </article>

      <aside className="op-aside" aria-label="Decision">
        <ProposedCreditCard controller={controller} items={items} />
      </aside>
    </>
  )
}

const ReviewRecord: React.FC = () => {
  const { reviewId } = useParams()
  return <ReviewRecordPage key={reviewId} />
}

export default ReviewRecord
