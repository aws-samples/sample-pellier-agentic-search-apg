import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchConciergeSession, OperatorApiError, type ConciergeSession } from '../../../services/operator'
import ServiceIdentity from '../../../shared/ServiceIdentity'
import { redirectToSignIn } from '../../../utils/auth'
import './OperatorTurnEvidence.css'

/**
 * Read the exact persisted Operator turn. The existing operator endpoint owns
 * authorization and customer scope; navigation state never supplies evidence.
 */
export default function OperatorTurnEvidence() {
  const [params] = useSearchParams()
  const customerId = params.get('customer')?.trim() ?? ''
  const sessionId = params.get('session')?.trim() ?? ''
  const turnId = params.get('turn')?.trim() ?? ''
  const [session, setSession] = useState<ConciergeSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [needsSignIn, setNeedsSignIn] = useState(false)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    setSession(null)
    setError(null)
    setNeedsSignIn(false)
    if (!customerId || !sessionId || !turnId) {
      setLoading(false)
      return
    }
    setLoading(true)
    void fetchConciergeSession(customerId, sessionId)
      .then(record => {
        if (!active) return
        if (record.customerId !== customerId || record.sessionId !== sessionId) {
          throw new Error('The returned record does not match this customer and session.')
        }
        setSession(record)
      })
      .catch((reason: unknown) => {
        if (!active) return
        setNeedsSignIn(reason instanceof OperatorApiError && reason.needsOperatorSignIn)
        setError(reason instanceof Error ? reason.message : 'The recorded turn is unavailable.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [customerId, sessionId, turnId, revision])

  const request = session?.messages.find(message => message.turnId === turnId && message.role === 'user')
  const answer = session?.messages.find(message => message.turnId === turnId && message.role === 'assistant')
  const artifact = answer?.artifact
  const steps = artifact?.investigation ?? []
  const evidence = artifact?.evidence ?? []
  const back = customerId ? `/operator/clients/${encodeURIComponent(customerId)}#operator-concierge` : '/operator'
  const missingSelection = !customerId || !sessionId || !turnId

  return (
    <div className="observatory-turn-workbench" data-testid="operator-turn-evidence">
      <header className="observatory-turn-heading">
        <div>
          <h1>Operator turn evidence</h1>
          <p>The request, service activity, and answer from one persisted conversation.</p>
        </div>
        <Link className="pellier-action-quiet" to={back}>Return to client</Link>
      </header>
      {loading ? <p role="status">Reading the recorded turn…</p> : null}
      {missingSelection ? <p role="status">Open this view from an Operator conversation to inspect a specific turn.</p> : null}
      {error ? (
        <div className="observatory-turn-state" role="alert">
          <h2>{needsSignIn ? 'Operator sign-in required' : 'This turn could not be read'}</h2>
          <p>{needsSignIn ? 'The conversation retains the Operator access boundary in Observatory.' : error}</p>
          <button className="pellier-action" type="button" onClick={() => needsSignIn ? redirectToSignIn('email') : setRevision(value => value + 1)}>
            {needsSignIn ? 'Sign in as an operator' : 'Try again'}
          </button>
        </div>
      ) : null}
      {!loading && session && !request && !answer ? (
        <p className="observatory-turn-state" role="status">This turn is not present in the returned conversation. No other turn has been substituted.</p>
      ) : null}
      {session && (request || answer) ? (
        <>
          <div className="observatory-turn-context">
            <span>Client <code>{session.customerId}</code></span>
            <span>Turn <code>{turnId}</code></span>
            <span>Source: persisted Operator conversation</span>
          </div>
          <div className="observatory-turn-grid">
            <section className="observatory-turn-panel">
              <header><h2>Operator request</h2><p>The original question</p></header>
              <div className="observatory-turn-content">
                <p className="observatory-turn-request">{request?.content ?? 'The request text is not in the returned record.'}</p>
                {artifact?.shopperHandoff ? (
                  <div className="observatory-turn-handoff">
                    <h3>Shopper context</h3>
                    <p>{artifact.shopperHandoff.shopperRequest}</p>
                    <small>Reported context. Account facts and permissions are established separately.</small>
                  </div>
                ) : null}
              </div>
            </section>
            <section className="observatory-turn-panel">
              <header><h2>Service activity</h2><p>Only operations recorded for this turn</p></header>
              <div className="observatory-turn-content">
                {steps.length ? <ol className="observatory-turn-steps">
                  {steps.map((step, index) => (
                    <li key={`${step.kind}-${index}`} data-status={step.status}>
                      <details open={index === 0}>
                        <summary><strong>{step.label}</strong><span>{step.status}</span></summary>
                        <div className="observatory-turn-step-detail">
                          <ServiceIdentity source={step.source} />
                          {step.result ? <p>{step.result}</p> : null}
                          {step.durationMs != null ? <code>{step.durationMs} ms</code> : null}
                        </div>
                      </details>
                    </li>
                  ))}
                </ol> : <p>No service activity was recorded in this turn artifact.</p>}
                {artifact?.sources?.length ? <div className="observatory-turn-sources">
                  {artifact.sources.map(source => <div key={source.source}>
                    <ServiceIdentity source={source.source} />
                    <p>{source.detail}</p>
                  </div>)}
                </div> : null}
              </div>
            </section>
            <section className="observatory-turn-panel">
              <header><h2>Recorded answer</h2><p>{answer?.turnState || 'No answer recorded'}</p></header>
              <div className="observatory-turn-content">
                {artifact?.primaryLabel ? <p className="observatory-turn-label">{artifact.primaryLabel}</p> : null}
                <p>{answer?.content ?? 'This request has no persisted answer yet.'}</p>
                {artifact?.primaryNote ? <p>{artifact.primaryNote}</p> : null}
                {artifact?.recommendation?.body ? <div className="observatory-turn-handoff">
                  <h3>Recommendation</h3><p>{artifact.recommendation.body}</p>
                </div> : null}
                {artifact?.proposedActions?.filter(action => action.reviewId != null).map(action => (
                  <Link key={action.reviewId} className="pellier-action-quiet" to={`/operator/reviews/${action.reviewId}`}>
                    Open review {action.reviewId}
                  </Link>
                ))}
              </div>
            </section>
          </div>
          {evidence.length ? <section className="observatory-turn-panel observatory-turn-facts">
            <header><h2>Evidence and its role</h2><p>Facts, reported context, and inference remain distinct.</p></header>
            <dl>
              {evidence.map((item, index) => <div key={`${item.kind}-${index}`}>
                <dt>{item.label ?? item.kind}<span>{item.role ?? 'fact'} · {item.status}</span></dt>
                <dd><ServiceIdentity source={item.source} />{item.note ? <p>{item.note}</p> : null}{item.recordId ? <code>{item.recordId}</code> : null}</dd>
              </div>)}
            </dl>
          </section> : null}
          {artifact ? <details className="observatory-turn-raw">
            <summary>Recorded artifact</summary>
            <pre>{JSON.stringify(artifact, null, 2)}</pre>
          </details> : null}
        </>
      ) : null}
    </div>
  )
}
