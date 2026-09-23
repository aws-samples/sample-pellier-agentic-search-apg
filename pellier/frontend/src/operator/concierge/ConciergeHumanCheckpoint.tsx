import React, { useMemo, useState } from 'react'
import { CheckCircle2, ShieldCheck, UserCheck } from 'lucide-react'

import type {
  OperatorClientRecord,
  OperatorOrder,
} from '../../services/operator'

const RETURN_REASONS = [
  ['damaged', 'Damaged'],
  ['wrong_size', 'Wrong size'],
  ['not_as_described', 'Not as described'],
  ['changed_mind', 'Changed mind'],
  ['other', 'Other'],
] as const

/**
 * The disputed pieces a reviewer can still prepare a return for: the ticket names
 * them and no return record exists yet. Once the robe is recorded, the catchall is
 * the remaining question.
 */
export function returnCandidates(record: OperatorClientRecord): OperatorOrder[] {
  const unrecorded = record.client.returnEvidence?.unrecordedDisputedProductIds
  if (unrecorded) {
    return record.orders.filter((order) => unrecorded.includes(order.productId)).slice(0, 3)
  }
  const ticketText = record.tickets
    .filter((ticket) => ticket.status === 'open' || ticket.status === 'pending')
    .map((ticket) => `${ticket.subject} ${ticket.lastNote}`)
    .join(' ')
    .toLowerCase()
  const stop = new Set(['pellier', 'luxury', 'bath', 'sage'])
  const mentioned = record.orders.filter((order) =>
    order.productName
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .some(
        (token) =>
          token.length >= 4 &&
          !stop.has(token) &&
          ticketText.includes(token),
      ),
  )
  return (mentioned.length ? mentioned : record.orders.slice(0, 2)).slice(0, 3)
}

interface Props {
  record: OperatorClientRecord
  disabled: boolean
  onPrepare: (request: string) => void
}

const ConciergeHumanCheckpoint: React.FC<Props> = ({
  record,
  disabled,
  onPrepare,
}) => {
  const items = useMemo(() => returnCandidates(record), [record])
  // Both choices belong to the person; candidate order must not choose an item.
  const [productId, setProductId] = useState('')
  const [reason, setReason] = useState('')
  const item = items.find((candidate) => candidate.productId === productId)

  if (!record.client.returnEvidence?.unconfirmedReturnAssertion || !items.length) {
    return null
  }

  return (
    <section
      className="operator-concierge-human-checkpoint"
      data-testid="operator-concierge-human-checkpoint"
      aria-labelledby="operator-concierge-checkpoint-title"
    >
      <div className="operator-concierge-human-checkpoint-head">
        <h3 id="operator-concierge-checkpoint-title">
          Prepare a return review
        </h3>
        <p>
          This prepares a review. It does not authorize or execute the return.
        </p>
      </div>

      <ol className="operator-concierge-boundary">
        <li data-state="current">
          <UserCheck size={16} aria-hidden="true" />
          <span><strong>You choose</strong> the exact item and reason</span>
        </li>
        <li>
          <CheckCircle2 size={16} aria-hidden="true" />
          <span><strong>You confirm or decline</strong> on the review in Action Queue</span>
        </li>
        <li>
          <ShieldCheck size={16} aria-hidden="true" />
          <span><strong>Policy and Aurora</strong> decide execution later</span>
        </li>
      </ol>

      <fieldset className="operator-concierge-human-checkpoint-items" disabled={disabled}>
        <legend>Choose the disputed piece</legend>
        {items.map((candidate) => (
          <label key={`${candidate.orderId}-${candidate.productId}`}>
            <input
              type="radio"
              name="service-recovery-item"
              value={candidate.productId}
              checked={candidate.productId === productId}
              onChange={(event) => setProductId(event.target.value)}
            />
            <span>
              <strong>{candidate.productName}</strong>
              <small>
                Order #{candidate.orderId}, ${candidate.price.toFixed(2)}
              </small>
            </span>
          </label>
        ))}
      </fieldset>

      <label className="operator-concierge-human-checkpoint-reason">
        <span>Return reason</span>
        <select
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          disabled={disabled}
          required
          aria-describedby="operator-concierge-checkpoint-reason-note"
        >
          <option value="" disabled>
            Select the customer&rsquo;s stated reason
          </option>
          {RETURN_REASONS.map(([value, label]) => (
            <option value={value} key={value}>{label}</option>
          ))}
        </select>
      </label>
      <p
        id="operator-concierge-checkpoint-reason-note"
        className="operator-concierge-human-checkpoint-reason-note"
      >
        Use the reason the customer stated. Pellier never fills it in.
      </p>

      <button
        type="button"
        className="operator-concierge-human-checkpoint-action"
        disabled={disabled || !item || !reason}
        aria-describedby={reason ? undefined : 'operator-concierge-checkpoint-reason-note'}
        onClick={() => {
          if (!item || !reason) return
          // The canonical code travels verbatim, so the backend never has to
          // infer the reason from paraphrase.
          onPrepare(
            `Prepare the return for "${item.productName}" on order ` +
              `#${item.orderId} for review. Customer's stated reason: ${reason}.`,
          )
        }}
      >
        Prepare review
      </button>
      <p className="operator-concierge-primary-note">
        A direct link to the saved review will appear here. You can then inspect
        the evidence and record your decision in Action Queue.
      </p>
    </section>
  )
}

export default ConciergeHumanCheckpoint
