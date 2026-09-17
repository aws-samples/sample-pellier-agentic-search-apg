import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchReplacements, OperatorApiError, type ReplacementRecovery } from '../../../services/operator'
import ServiceIdentity from '../../../shared/ServiceIdentity'
import { redirectToSignIn } from '../../../utils/auth'
import ReferenceBrief from '../../components/ReferenceBrief'
import './OperatorTurnEvidence.css'

/** Exact, operator-authorized Aurora record. A navigation parameter is not evidence. */
export default function ReplacementEvidence() {
  const [params] = useSearchParams()
  const customer = params.get('customer')?.trim() ?? ''
  const replacement = params.get('replacement')?.trim() ?? ''
  const [data, setData] = useState<ReplacementRecovery | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    setData(null)
    setError(null)
    if (!customer || !replacement) { setLoading(false); return }
    setLoading(true)
    fetchReplacements(customer, replacement).then(value => { if (active) setData(value) })
      .catch(reason => { if (active) setError(reason) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [customer, replacement, revision])

  const record = data?.replacements.find(row => row.replacementId === replacement)
  const signIn = error instanceof OperatorApiError && error.needsOperatorSignIn
  const back = customer ? `/operator/clients/${encodeURIComponent(customer)}#operator-replacement-care` : '/operator'
  return <div className="observatory-turn-workbench" data-testid="replacement-evidence">
    <header className="observatory-turn-heading">
      <div><h1>Replacement recovery</h1><p>Follow one approved remedy through its durable records.</p></div>
      <Link className="pellier-action-quiet" to={back}>Return to client</Link>
    </header>
    <ReferenceBrief id="replacement" />
    {!customer || !replacement ? <p role="status">Open this view from Replacement care in the Operator client record to inspect an exact operation.</p> : null}
    {loading ? <p role="status">Reading the recovery evidence…</p> : null}
    {error ? <div className="observatory-turn-state" role="alert">
      <h2>{signIn ? 'Operator sign-in required' : 'Recovery evidence is unavailable'}</h2>
      <p>{signIn ? 'This record retains the Operator access boundary.' : 'The outcome cannot be established from this response. Check the same operation again.'}</p>
      <button className="pellier-action" onClick={() => signIn ? redirectToSignIn('email') : setRevision(value => value + 1)}>
        {signIn ? 'Sign in as an operator' : 'Try again'}
      </button>
    </div> : null}
    {data && !data.available ? <p role="status">Replacement care is not enabled in this deployment.</p> : null}
    {data?.available && !record ? <p role="status">This replacement was not found for this client. No other operation has been substituted.</p> : null}
    {record ? <>
      <div className="observatory-turn-context">
        <span>Client <code>{customer}</code></span><span>Replacement <code>{record.replacementId}</code></span>
        <span>Recorded state: {record.state.replace(/_/g, ' ')}</span>
      </div>
      <p>Fulfillment uses the workshop simulator. “Shipped” records a simulator outcome, not a real carrier shipment. Workflow status alone does not establish fulfillment.</p>
      <div className="observatory-turn-grid">
        <section className="observatory-turn-panel">
          <header><h2>Approved remedy</h2><p>Exact terms and one stable operation</p></header>
          <div className="observatory-turn-content">
            <ServiceIdentity source="Amazon Aurora" />
            <h3>{record.productName}</h3>
            <p>Order #{record.orderId}. Quantity {record.quantity}. The damaged item requires inspection.</p>
            <p>Approval #{record.reviewId}</p>
            <Link className="pellier-action-quiet" to={`/operator/reviews/${record.reviewId}`}>Inspect human decision and policy</Link>
            <details><summary>Operation identifiers</summary>
              <p>Idempotency key <code>{record.idempotencyKey}</code></p>
              <p>Approval fingerprint <code>{record.approvalHash}</code></p>
            </details>
          </div>
        </section>
        <section className="observatory-turn-panel">
          <header><h2>Fulfillment handoff</h2><p>The outbox and its recorded delivery</p></header>
          <div className="observatory-turn-content">
            {record.executionArn ? <ServiceIdentity source="AWS Step Functions" /> : <ServiceIdentity source="Amazon Aurora" />}
            {record.outbox ? <>
              <p>Outbox event <code>{record.outbox.eventId}</code></p>
              <p>{record.outbox.attempts} delivery attempts. {record.outbox.publishedAt ? 'Workflow handoff recorded.' : 'Workflow handoff has not been recorded.'}</p>
            </> : <p>No outbox record was returned. Check the database before retrying.</p>}
            <p>Provider operation: <code>{record.providerOperationId ?? 'Not recorded'}</code></p>
            {record.workflowResolution === 'operator_review_required' ? <div role="status">
              <h3>Operator follow-up required</h3>
              <p>Aurora records an unresolved workflow. Keep the existing provider operation and check its outcome before preparing another remedy.</p>
            </div> : null}
            {record.executionArn ? <details><summary>Workflow execution</summary><code>{record.executionArn}</code></details> : null}
          </div>
        </section>
        <section className="observatory-turn-panel">
          <header><h2>Recorded events</h2><p>Persisted observations, in database order</p></header>
          <div className="observatory-turn-content">
            {record.events.length ? <ol className="observatory-turn-steps">{record.events.map((event, index) =>
              <li key={`${event.type}-${index}`}><strong>{event.type.replace(/_/g, ' ')}</strong>
                <p><time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time></p>
              </li>,
            )}</ol> : <p>No events were returned.</p>}
            {record.state === 'outcome_unknown' ? <p role="status">Reconcile the existing provider operation. An interrupted response does not establish failure.</p> : null}
          </div>
        </section>
      </div>
    </> : null}
  </div>
}
