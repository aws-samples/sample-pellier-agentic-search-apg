import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  fetchReplacements, prepareReplacement, OperatorApiError,
  type OperatorClientRecord, type ReplacementRecovery,
} from '../../services/operator'
import ServiceIdentity from '../../shared/ServiceIdentity'
import './replacement-care.css'

const STATES = {
  reserved: 'Replacement reserved',
  awaiting_fulfillment: 'Awaiting fulfillment',
  outcome_unknown: 'Outcome needs checking',
  accepted: 'Accepted by fulfillment',
  shipped: 'Shipment recorded',
  operator_review_required: 'Operator follow-up required',
}

const ERRORS: Record<string, string> = {
  replacement_quantity_exceeds_order: 'The remaining eligible quantity has changed. Check this order’s return history.',
  replacement_order_not_found: 'This order is no longer available for this client.',
  replacement_not_installed: 'Replacement care is not enabled in this deployment.',
}

export default function ReplacementCare({ record }: { record: OperatorClientRecord }) {
  const navigate = useNavigate()
  const customerId = record.client.customerId
  const [data, setData] = useState<ReplacementRecovery | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [version, setVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [orderId, setOrderId] = useState(record.orders[0]?.orderId ?? 0)
  const [quantity, setQuantity] = useState(1)
  const [issue, setIssue] = useState('')
  const refresh = useCallback(() => setVersion(value => value + 1), [])

  useEffect(() => {
    let active = true
    setLoadError(false)
    fetchReplacements(customerId).then(value => {
      if (active) setData(value)
    }).catch(() => { if (active) setLoadError(true) })
    return () => { active = false }
  }, [customerId, version])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (busy || !data?.available || !issue.trim()) return
    setBusy(true)
    setError('')
    try {
      const result = await prepareReplacement(customerId, orderId, quantity, issue.trim())
      navigate(`/operator/reviews/${result.reviewId}`)
    } catch (err) {
      setError(err instanceof OperatorApiError
        ? ERRORS[err.code] ?? 'The proposal could not be confirmed. Retry with the same terms to find any review already prepared.'
        : 'The proposal could not be confirmed. Check the Action Queue before trying again.')
    } finally { setBusy(false) }
  }

  return <section className="operator-replacement-care operator-card" id="operator-replacement-care" aria-labelledby="replacement-care-title">
    <div className="operator-replacement-heading">
      <div>
        <h2 id="replacement-care-title">Replacement care</h2>
        <p>The agreed remedy, from review to fulfillment.</p>
      </div>
      <button type="button" className="operator-client-chat-link" onClick={refresh}>Check outcome</button>
    </div>
    {loadError ? <p role="status">The latest replacement record is unavailable. Check again before taking another action.</p>
      : !data ? <p role="status">Reading the replacement record…</p>
        : !data.available ? <p>Replacement care is not enabled in this deployment.</p>
          : data.replacements.length === 0 ? <p>No replacement has been committed for this client.</p>
            : <div className="operator-replacement-list">{data.replacements.map(replacement =>
              <article key={replacement.replacementId} className="operator-replacement-item">
                <div className="operator-replacement-heading">
                  <h3>{replacement.productName}</h3>
                  <span className="operator-replacement-state" data-state={replacement.state}>{STATES[replacement.state]}</span>
                </div>
                <p>Order #{replacement.orderId} · {replacement.quantity} {replacement.quantity === 1 ? 'piece' : 'pieces'} · Damaged item requires inspection</p>
                <ol className="operator-replacement-events">{replacement.events.map((event, index) =>
                  <li key={`${event.type}-${index}`}>
                    <span>{STATES[event.type as keyof typeof STATES] ?? event.type.replace(/_/g, ' ')}</span>
                    <time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time>
                  </li>,
                )}</ol>
                {replacement.state === 'outcome_unknown' ? <p role="status">An interrupted response does not establish whether fulfillment accepted this request. Reconcile the existing operation before preparing another.</p> : null}
                {replacement.workflowResolution === 'operator_review_required' ? <div className="operator-replacement-follow-up" role="status">
                  <strong>Operator follow-up required</strong>
                  <p>Automatic fulfillment needs attention. The recorded provider state still applies. Check this operation’s evidence before agreeing another remedy.</p>
                </div> : null}
                <div className="operator-replacement-sources">
                  <ServiceIdentity source="Amazon Aurora" />
                  {replacement.executionArn ? <ServiceIdentity source="AWS Step Functions" /> : null}
                </div>
                <p className="operator-cell-note">Fulfillment provider: workshop simulator. This record does not describe a real shipment.</p>
                <div className="operator-review-client-actions">
                  <Link className="operator-client-chat-link" to={`/operator/reviews/${replacement.reviewId}`}>Open decision</Link>
                  <Link className="operator-client-chat-link" to={`/observatory/replacement?customer=${encodeURIComponent(customerId)}&replacement=${encodeURIComponent(replacement.replacementId)}`}>Inspect recovery evidence</Link>
                </div>
              </article>,
            )}</div>}
    {data?.available && !loadError && record.orders.length > 0 ? <details className="operator-replacement-prepare">
      <summary>Prepare a damaged-item replacement</summary>
      <p>This prepares exact terms for a separate human decision. Stock is checked again when the approved action executes.</p>
      <form onSubmit={submit}>
        <label htmlFor="replacement-order">Order and piece</label>
        <select id="replacement-order" value={orderId} onChange={event => setOrderId(Number(event.target.value))} disabled={busy}>
          {record.orders.map(order => <option key={order.orderId} value={order.orderId}>#{order.orderId} · {order.productName}</option>)}
        </select>
        <label htmlFor="replacement-quantity">Quantity</label>
        <input id="replacement-quantity" type="number" min={1} max={record.orders.find(order => order.orderId === orderId)?.quantity ?? 1} value={quantity} onChange={event => setQuantity(Number(event.target.value))} required disabled={busy} />
        <label htmlFor="replacement-issue">What did the client report?</label>
        <textarea id="replacement-issue" rows={3} maxLength={500} value={issue} onChange={event => setIssue(event.target.value)} required disabled={busy} />
        <p className="operator-cell-note">The damaged piece requires inspection. No credit or shipping date is included. Approval is valid for 24 hours before first execution.</p>
        {error ? <p role="alert">{error}</p> : null}
        <button className="operator-button" type="submit" disabled={busy || !issue.trim()}>{busy ? 'Preparing review…' : 'Prepare for review'}</button>
      </form>
    </details> : null}
  </section>
}
