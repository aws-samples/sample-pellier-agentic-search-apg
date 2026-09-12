import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useReviewQueue } from '../hooks/useReviewQueue'
import { outcomeKind, outcomeLine } from '../surfaces/ReviewQueue'
import ClientAvatar from './ClientAvatar'

/** The same authenticated queue resource as the desk, beside the open case. */
export default function ReviewQueuePanel() {
  const { queue, error } = useReviewQueue()
  const [query, setQuery] = useState('')
  const needle = query.trim().toLowerCase()
  const reviews = queue?.reviews.filter(review =>
    [review.customerName, review.productName, review.issue, String(review.reviewId)]
      .filter(Boolean).join(' ').toLowerCase().includes(needle),
  ) ?? []

  return (
    <aside className="operator-queue-panel" aria-label="Review queue">
      <div className="operator-queue-panel-heading">
        <h2>Review desk</h2>
        {queue ? <span>{queue.pendingCount} pending</span> : null}
      </div>
      <label className="operator-queue-search">
        <Search size={16} aria-hidden="true" />
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Find a client or piece"
          aria-label="Find a review"
        />
      </label>
      {error ? <p className="operator-queue-panel-note" role="status">
        {queue ? 'Refresh unavailable. Showing the last successful read.' : 'The review queue is unavailable.'}
      </p> : !queue ? <p className="operator-queue-panel-note" role="status">Reading the queue…</p> : null}
      <div className="operator-queue-cards">
        {reviews.map(review => (
          <NavLink
            key={review.reviewId}
            to={`/operator/reviews/${review.reviewId}`}
            className="operator-queue-card"
            data-outcome={outcomeKind(review)}
          >
            <span className="operator-queue-card-person">
              <ClientAvatar customerId={review.customerId} name={review.customerName} personaId={review.personaId} />
              <span><strong>{review.customerName}</strong><small>Review {review.reviewId}</small></span>
            </span>
            <span className="operator-queue-card-piece">{review.productName || review.issue || 'Prepared action'}</span>
            <span className="operator-queue-card-outcome">{outcomeLine(review)}</span>
          </NavLink>
        ))}
      </div>
      {queue && !reviews.length ? <p className="operator-queue-panel-note">
        {needle ? 'No reviews match this client or piece.' : 'No prepared actions in the queue.'}
      </p> : null}
    </aside>
  )
}
