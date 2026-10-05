/**
 * One client record: the ticket, the orders with their return state, the
 * store credits, and beside it the investigation.
 *
 * Consequential actions are deliberately absent from the record itself. The
 * Planner opens one review, a person approves it, and only the approved review
 * can reach execution.
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { StatusTag } from '../../components/turn'
import {
  fetchClientRecord,
  OperatorApiError,
  type OperatorClientRecord,
  type OperatorReview,
} from '../../services/operator'
import { imageSrc } from '../../utils/assetPath'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState, { describeOperatorError } from '../components/OperatorState'
import { useInvestigation } from '../hooks/useInvestigation'
import { useReview } from '../hooks/useReview'
import InvestigationSteps from '../investigation/InvestigationSteps'
import { shortDate } from './ClientBook'
import { requestOutcome } from './ReviewQueue'

function ticketTone(status: string): 'good' | 'blocked' | 'pending' {
  if (status === 'open' || status === 'pending') return 'pending'
  return 'good'
}

function ticketWord(status: string): string {
  if (status === 'open') return 'Open'
  if (status === 'pending') return 'Pending'
  if (status === 'resolved') return 'Resolved'
  return 'Closed'
}

/** The review the record follows: the open one, else the newest. */
export function activeReview(reviews: OperatorReview[]): OperatorReview | null {
  return reviews.find(r => r.humanState === 'confirmation_required') ?? reviews[0] ?? null
}

function reviewTone(review: OperatorReview): { tone: 'good' | 'blocked' | 'pending'; word: string; pulse: boolean } {
  if (review.humanState === 'declined') return { tone: 'blocked', word: 'Declined', pulse: false }
  if (review.humanState === 'confirmed') {
    if (review.assurance.aurora === 'PERMITTED' && review.assurance.evidence === 'RECEIPTED') {
      return { tone: 'good', word: 'Credited', pulse: false }
    }
    if (review.assurance.policy === 'DENY') return { tone: 'blocked', word: 'Denied by policy', pulse: false }
    if (review.assurance.evidence === 'NO_EXECUTION') {
      return { tone: 'blocked', word: 'Not written', pulse: false }
    }
    return { tone: 'good', word: 'Approved', pulse: false }
  }
  return { tone: 'pending', word: 'Waiting for approval', pulse: true }
}

const OrderThumb: React.FC<{ src: string; name: string }> = ({ src, name }) => {
  const [failed, setFailed] = useState(false)
  const resolved = imageSrc(src)
  if (!resolved || failed) {
    return <span className="op-thumb-fallback" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
  }
  return <img src={resolved} alt="" aria-hidden="true" className="op-thumb" loading="lazy" decoding="async" onError={() => setFailed(true)} />
}

const ClientRecordPage: React.FC = () => {
  const { customerId = '' } = useParams()
  const [record, setRecord] = useState<OperatorClientRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const investigation = useInvestigation(customerId)
  const followed = record ? activeReview(record.reviews) : null
  const reviewId = investigation.answer?.proposal?.reviewId ?? followed?.reviewId ?? null
  const review = useReview(reviewId)

  const load = useCallback(() => {
    let active = true
    setError(null)
    fetchClientRecord(customerId)
      .then(data => { if (active) setRecord(data) })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof OperatorApiError ? reason.code : 'operator_unavailable')
      })
    return () => { active = false }
  }, [customerId])

  useEffect(load, [load, retry])

  // A decision or an execution changes the credits and the review the record
  // shows, so the record is re-read when the review's own read completes.
  const reviewVersion = review.detail?.review.humanState ?? ''
  const executed = review.detail?.record?.creditRows ?? 0
  useEffect(() => {
    if (!reviewVersion) return
    setRetry(value => value + 1)
  }, [reviewVersion, executed])

  const start = useCallback(() => {
    void investigation.start().then(() => setRetry(value => value + 1))
  }, [investigation])

  if (error) {
    const described = describeOperatorError(error, 'open this client record')
    return (
      <OperatorState
        level={1}
        data-testid="operator-record-error"
        eyebrow="Client record"
        headline={described.headline}
        body={described.body}
        reason={error}
        action={described.signIn
          ? <OperatorSignInAction unlocks="open this client record" />
          : error !== 'operator_group_required'
            ? <button type="button" className="op-button op-button-quiet" onClick={() => setRetry(v => v + 1)}>Try again</button>
            : undefined}
      />
    )
  }
  if (!record) {
    return <OperatorState level={1} data-testid="operator-record-loading" eyebrow="Client record" headline="Reading the record" busy />
  }

  const { client, orders, tickets, credits, requests } = record
  const openTickets = tickets.filter(t => t.status === 'open' || t.status === 'pending')
  const items = orders.filter(o => o.returned).map(o => o.productName)

  return (
    <>
      <article className="op-record" data-testid="operator-record" aria-labelledby="op-record-title">
        <header className="op-record-head">
          <ClientAvatar customerId={client.customerId} name={client.name} personaId={client.personaId} size="lg" />
          <div>
            <p className="op-eyebrow">Client</p>
            <h1 id="op-record-title" className="op-h1">{client.name}</h1>
            <p className="op-record-meta">
              <code>{client.customerId}</code>
              {/* A plain link in a new tab. It signs nobody in: a shopper
                  signs in from their card on the storefront, so Nadia stays
                  signed in here. */}
              {client.personaId ? (
                <Link to="/" target="_blank" rel="noopener noreferrer" className="op-link" data-testid="operator-storefront-handoff">
                  Open the storefront<span className="gov-visually-hidden"> (opens in a new tab)</span>
                </Link>
              ) : null}
            </p>
          </div>
        </header>

        <section className="op-card" data-testid="operator-tickets" aria-labelledby="op-ticket-title">
          <div className="op-card-head">
            <h2 id="op-ticket-title" className="op-h2">Ticket</h2>
            <span className="op-list-count">{tickets.length}</span>
          </div>
          {tickets.length === 0 ? <p className="op-note">No tickets on file.</p> : null}
          {tickets.map(ticket => (
            <div key={ticket.ticketId} className="op-ticket" data-status={ticket.status} data-testid="operator-ticket">
              <div className="op-ticket-head">
                <code>{ticket.ticketId}</code>
                <StatusTag tone={ticketTone(ticket.status)}>{ticketWord(ticket.status)}</StatusTag>
                {shortDate(ticket.openedAt) ? <span className="op-row-sub">{shortDate(ticket.openedAt)}</span> : null}
              </div>
              <p className="op-ticket-subject">{ticket.subject}</p>
              <p className="op-ticket-note">{ticket.lastNote}</p>
            </div>
          ))}
          {requests.map(request => {
            const outcome = requestOutcome(request)
            return (
              <div key={request.requestId} className="op-ticket" data-status={request.status} data-testid="operator-credit-request">
                <div className="op-ticket-head">
                  <span className="op-row-name">Asked in chat</span>
                  <StatusTag tone={outcome.tone}>{outcome.word}</StatusTag>
                  {shortDate(request.requestedAt) ? <span className="op-row-sub">{shortDate(request.requestedAt)}</span> : null}
                </div>
                <p className="op-ticket-subject">Store credit request, no amount</p>
                {request.issue ? <p className="op-ticket-note">{request.issue}</p> : null}
                {request.answeredByReviewId ? (
                  <Link to={`/operator/reviews/${request.answeredByReviewId}`} className="op-link">Open the review that answered it</Link>
                ) : null}
              </div>
            )
          })}
        </section>

        <section className="op-card" data-testid="operator-orders" aria-labelledby="op-orders-title">
          <div className="op-card-head">
            <h2 id="op-orders-title" className="op-h2">Orders</h2>
            <span className="op-list-count">{orders.length}</span>
          </div>
          {orders.length === 0 ? <p className="op-note">No orders on record.</p> : (
            <table className="op-table">
              <thead>
                <tr>
                  <th scope="col"><span className="gov-visually-hidden">Photo</span></th>
                  <th scope="col">Item</th>
                  <th scope="col" className="op-col-optional">Placed</th>
                  <th scope="col" className="op-num">Paid</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(order => (
                  <tr key={order.orderId} data-returned={order.returned ? 'true' : 'false'} data-testid={`operator-order-${order.orderId}`}>
                    <td><OrderThumb src={order.imageUrl} name={order.productName} /></td>
                    <td>
                      <span className="op-item-name">{order.productName}</span>
                      <span className="op-row-sub">{order.brand}</span>
                    </td>
                    <td className="op-col-optional">{shortDate(order.placedAt) ?? ''}</td>
                    <td className="op-num">${order.amountPaid}</td>
                    <td>
                      {order.returned
                        ? <StatusTag tone="blocked">Returned</StatusTag>
                        : <StatusTag tone="good">Delivered</StatusTag>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="op-card" data-testid="operator-credits" aria-labelledby="op-credits-title">
          <div className="op-card-head">
            <h2 id="op-credits-title" className="op-h2">Store credits</h2>
            {client.creditBalanceCents > 0 ? <span className="op-list-count">${client.creditBalance}</span> : null}
          </div>
          {credits.length === 0 ? (
            <p className="op-note" data-testid="operator-credits-none">No credit recorded.</p>
          ) : (
            <table className="op-table">
              <thead>
                <tr>
                  <th scope="col">Reason</th>
                  <th scope="col" className="op-col-optional">Issued</th>
                  <th scope="col">Key</th>
                  <th scope="col" className="op-num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {credits.map(credit => (
                  <tr key={credit.creditId} data-testid={`operator-credit-${credit.creditId}`}>
                    <td>{credit.reason}</td>
                    <td className="op-col-optional">{shortDate(credit.createdAt) ?? ''}</td>
                    <td><code>{credit.idempotencyKey}</code></td>
                    <td className="op-num">${credit.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {followed ? (
            <p className="op-review-line" data-testid="operator-record-review">
              <StatusTag tone={reviewTone(followed).tone} pulse={reviewTone(followed).pulse}>{reviewTone(followed).word}</StatusTag>
              <span>${followed.amount} store credit, {followed.reason}</span>
              <Link to={`/operator/reviews/${followed.reviewId}`} className="op-link">Open the review</Link>
            </p>
          ) : null}
        </section>
      </article>

      <aside className="op-aside" aria-label="Investigation">
        <InvestigationSteps
          investigation={investigation}
          review={reviewId !== null ? review : null}
          onStart={start}
          hasOpenReview={Boolean(followed) && openTickets.length > 0}
        />
        {items.length > 0 && investigation.phase === 'idle' && !followed ? (
          <p className="op-note op-aside-note">
            {items.length === 1 ? '1 item went back' : `${items.length} items went back`}: {items.join(' and ')}. No credit recorded.
          </p>
        ) : null}
      </aside>
    </>
  )
}

const ClientRecord: React.FC = () => {
  const { customerId } = useParams()
  return <ClientRecordPage key={customerId} />
}

export default ClientRecord
