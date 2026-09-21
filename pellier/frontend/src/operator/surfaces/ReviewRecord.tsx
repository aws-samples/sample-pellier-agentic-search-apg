/**
 * One prepared request, and the decision it needs.
 *
 * Reading order is the operator's reasoning order: who the client is, what they
 * reported, what they actually bought, what Pellier proposes and why, the exact
 * action with its parameters, then the decision — and only then the four
 * assurance axes.
 *
 * Everything factual on this page is hydrated by the API from the table that
 * owns it. The review row supplies references and workflow state; membership,
 * spend, the order, live stock, and the client's return history are read at
 * request time. That is why there are no literals for Theo's rung or his spend
 * anywhere in this file.
 *
 * Confirming records that a person agreed to these parameters. It does not carry
 * the action out, and this page must never imply otherwise: the assurance axes
 * come from the API and are printed as given.
 */

import { CheckCircle2, CircleX, LoaderCircle } from 'lucide-react'
import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { MEMBERSHIP } from '../../data/membership'
import { imageSrc } from '../../utils/assetPath'
import {
  confirmReview,
  declineReview,
  executeReview,
  fetchReview,
  OperatorApiError,
  type OperatorExecutionResult,
  type OperatorReviewDetail, requesterLine } from '../../services/operator'
import ActionAssurance from '../components/ActionAssurance'
import ClientAvatar from '../components/ClientAvatar'
import OperatorSignInAction from '../components/OperatorSignInAction'
import OperatorState from '../components/OperatorState'
import MembershipRung from '../components/MembershipRung'
import ShopperHandoffView from '../components/ShopperHandoffView'
import { useOperatorQueueRefresh } from '../shell/OperatorFrame'
import { conversationHref } from '../concierge/conversationLinks'

function money(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function centsToMoney(cents: number): string {
  return money(cents / 100)
}

/** Parameter names as an operator reads them, not as the tool declares them. */
const PARAMETER_LABELS: Record<string, string> = {
  customer_id: 'Client',
  product_id: 'Product',
  reason: 'Reason',
  amount_cents: 'Amount',
  order_id: 'Order',
  quantity: 'Quantity',
  disposition: 'Damaged item handling',
}

const ACTION_TITLES: Record<string, string> = {
  initiate_return: 'File a return',
  issue_credit: 'Issue a goodwill credit',
  replace_damaged_item: 'Replace a damaged piece',
}

/**
 * The headline, with the review's own reason in it.
 *
 * The map used to read "File a damaged return" for every `initiate_return`, which
 * was true only while `damaged` was the sole scenario. A Concierge-prepared
 * not-as-described return rendered a headline naming a reason the review does not
 * carry — the narrative disagreeing with the parameters directly beneath it.
 */
function actionTitle(action: string, parameters: Record<string, unknown>): string {
  const base = ACTION_TITLES[action] ?? action
  const reason = parameters.reason
  if (action === 'initiate_return' && typeof reason === 'string' && reason) {
    return `File a ${reason.replace(/_/g, ' ')} return`
  }
  return base
}

function formatParameter(
  key: string,
  value: unknown,
  order?: { productId: string; productName: string } | null,
): string {
  if (key === 'amount_cents' && typeof value === 'number') {
    return centsToMoney(value)
  }
  // The table's job is the exact bound value, so the id stays first; the
  // piece's name beside it costs nothing and spares a lookup.
  if (key === 'product_id' && order && String(order.productId) === String(value)) {
    return `${String(value)} · ${order.productName}`
  }
  if ((key === 'reason' || key === 'disposition') && typeof value === 'string') {
    return value.replace(/_/g, ' ')
  }
  return String(value)
}

/** The issue sentence: "<piece> <problem>", without repeating the piece. */
export function issueLine(productName: string | undefined, issue: string): string {
  const problem = (issue || '').trim()
  const piece = (productName || '').trim()
  if (!piece) return problem
  if (!problem) return piece
  // The issue already names the piece, either because it IS the name or because the
  // operator wrote a full sentence about it.
  if (problem.toLowerCase().includes(piece.toLowerCase())) return problem
  return `${piece} ${problem}`
}


const DECISION_ERROR_COPY: Record<string, string> = {
  parameters_changed:
    'The proposed values changed since this page loaded. Reload and read the new terms before confirming.',
  operator_sign_in_required:
    'A verified operator sign-in is required to decide this action.',
  authentication_required:
    'Your operator sign-in has expired. Sign in again to decide this action.',
  operator_group_required:
    'This signed-in account is not a member of the operator group, so it cannot decide this action.',
  review_not_found:
    'This prepared action no longer exists. Return to the Action Queue for the current list.',
  review_already_open:
    'Another operator already has this action open. Reload to see its current state.',
  review_already_decided:
    'This action already has a decision. Refresh the record to read it.',
  operator_unavailable:
    'The service response was unavailable. The request may have been recorded; refresh the record before continuing.',
  temporarily_unavailable:
    'The service response was unavailable. Refresh the record to establish the outcome.',
  governed_action_unavailable:
    'The governed action is not available right now, so nothing was recorded.',
  governed_rail_unavailable:
    'The governed rail is not available, so this action was not submitted and nothing ran. Restore the managed deployment before trying again.',
}

/** Plain-language decision failure; the raw code stays visible for the receipt. */
function describeDecisionError(code: string, missing: readonly string[] = []): string {
  const base = DECISION_ERROR_COPY[code] ?? `The outcome could not be verified (${code}). Refresh the record before continuing.`
  return missing.length ? `${base} Missing: ${missing.join(', ')}.` : base
}

const ReviewRecordPage: React.FC = () => {
  const { reviewId } = useParams<{ reviewId: string }>()
  const [params] = useSearchParams()
  const { user } = useAuth()
  const refreshQueue = useOperatorQueueRefresh()
  const [detail, setDetail] = useState<OperatorReviewDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deciding, setDeciding] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [decisionErrorMissing, setDecisionErrorMissing] = useState<readonly string[]>([])
  // THIS session's execution response. The durable record lives on the server in
  // `review.execution`, so a reload no longer loses the verdicts: this state only
  // makes the answer immediate for the operator who just pressed the button.
  const [execution, setExecution] = useState<OperatorExecutionResult | null>(null)
  const [executing, setExecuting] = useState(false)
  const [refreshNeeded, setRefreshNeeded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshNote, setRefreshNote] = useState<string | null>(null)

  const numericId = Number(reviewId)

  const load = useCallback(() => {
    let active = true
    if (!Number.isFinite(numericId)) {
      setError('review_not_found')
      return
    }
    fetchReview(numericId)
      .then((value) => {
        if (!active) return
        if (value.review.reviewId !== numericId) throw new Error('review_mismatch')
        setDetail(value)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(
          err instanceof OperatorApiError ? err.code : 'operator_unavailable',
        )
      })
    return () => { active = false }
  }, [numericId])

  useEffect(load, [load])

  const reconcile = async (committed = false) => {
    setRefreshing(true)
    try {
      const fresh = await fetchReview(numericId)
      if (fresh.review.reviewId !== numericId) throw new Error('review_mismatch')
      setDetail(fresh)
      setRefreshNeeded(false)
      setRefreshNote(null)
      setDecisionError(null)
    } catch {
      setRefreshNeeded(true)
      setRefreshNote(committed
        ? 'The response was recorded successfully. The latest record could not be loaded; refresh to continue.'
        : 'The latest record could not be loaded. Refresh to establish the outcome before continuing.')
    } finally {
      setRefreshing(false)
    }
  }

  const execute = async () => {
    if (!detail || executing || deciding || refreshNeeded) return
    setExecuting(true)
    setDecisionError(null)
    try {
      // The fingerprint is stale-view protection only. Every action parameter
      // comes from the persisted review, server-side.
      const outcome = await executeReview(
        detail.review.reviewId,
        detail.review.actionHash,
      )
      setExecution(outcome)
      // Re-read both projections from their owners. The detail fetch hydrates
      // the durable receipt; the shell fetch owns the queue count.
      refreshQueue()
      await reconcile(true)
    } catch (err: unknown) {
      setRefreshNeeded(true)
      setDecisionError(
        err instanceof OperatorApiError ? err.code : 'operator_unavailable',
      )
      setDecisionErrorMissing(err instanceof OperatorApiError ? err.missing : [])
    } finally {
      setExecuting(false)
    }
  }

  const decide = async (kind: 'confirm' | 'decline') => {
    if (!detail || deciding || executing || refreshNeeded) return
    setDeciding(true)
    setDecisionError(null)
    try {
      const decision = kind === 'confirm'
        // The fingerprint of the parameters shown above is echoed back. If any
        // material value moved since this page loaded, the server refuses rather
        // than applying the confirmation to different terms.
        ? await confirmReview(detail.review.reviewId, detail.review.actionHash)
        : await declineReview(detail.review.reviewId)
      setDetail({ ...detail, review: { ...detail.review, ...decision,
        status: kind === 'confirm' ? 'approved' : 'rejected',
      } })
      // The decision endpoint has committed at this point. Invalidate the
      // queue even if the following detail read is temporarily unavailable.
      refreshQueue()
      // Re-read rather than patching local state: the decision's authoritative
      // shape, including the assurance axes, comes from the server.
      await reconcile(true)
    } catch (err: unknown) {
      setRefreshNeeded(true)
      setDecisionError(
        err instanceof OperatorApiError ? err.code : 'operator_unavailable',
      )
    } finally {
      setDeciding(false)
    }
  }

  if (error) {
    const authenticationRequired =
      error === 'authentication_required' || error === 'invalid_credentials'
    const operatorRequired = error === 'operator_group_required'
    return (
      <OperatorState
        level={1}
        data-testid="operator-review-error"
        surface={authenticationRequired ? 'plate' : 'paper'}
        eyebrow="Prepared action"
        lead={
          <Link to="/operator/reviews" className="operator-back">
            Back to Action Queue
          </Link>
        }
        headline={
          authenticationRequired
            ? 'Operator sign-in required'
            : operatorRequired
              ? 'Operator access required'
              : error === 'review_not_found'
                ? 'No such action'
                : 'This prepared action is unavailable'
        }
        body={
          authenticationRequired ? (
            <>
              Sign in with the workshop operator account to read this prepared
              action. No database request was attempted.
            </>
          ) : operatorRequired ? (
            <>
              This signed-in account is not a member of the operator group. No
              database request was attempted.
            </>
          ) : undefined
        }
        reason={error}
        action={authenticationRequired ? <OperatorSignInAction unlocks="open this action" /> : undefined}
      />
    )
  }

  if (!detail) {
    return (
      <OperatorState
        level={1}
        data-testid="operator-review-loading"
        eyebrow="Prepared action"
        headline="Reading action details from Aurora…"
      />
    )
  }

  const {
    review,
    shopperHandoff,
    client,
    order,
    product,
    fulfilment,
    returns,
  } = detail
  const rung = MEMBERSHIP[client.membership]
  // Keep the conversation the operator came from, including when it surfaced
  // an already-open review. Never carry another client's navigation context.
  const sourceSession = params.get('client') === client.customerId
    ? params.get('session') : null
  const chatHref = conversationHref(client.customerId, sourceSession, params.get('turn'))
  const pending = review.humanState === 'confirmation_required'
  // The return this review produced is not part of the client's prior history. It is
  // identified by the write key the execution receipt carries, not by being the newest
  // — a timestamp comparison would misattribute a return filed seconds earlier by
  // someone else.
  const producedReturnId = review.execution?.producedReturnId ?? null
  const priorDamaged = returns.filter(
    (r) => r.reason === 'damaged' && r.returnId !== producedReturnId,
  )
  // This session's response first, then the stored receipt. Both describe the same
  // attempt; only the first is available the instant the button returns. Reading the
  // stored one is what stops the page offering "Execute this action" again after a
  // reload, and what keeps the rail sentence on screen.
  const attempted = execution ?? review.execution
  // One resolved set of axes for the whole page. This session's response if there is
  // one, otherwise the server's, which it resolves from the stored receipt.
  const axes = execution ? execution.assurance : review.assurance
  const phase = deciding
    ? ('recording_decision' as const)
    : executing
      ? ('executing' as const)
      : undefined
  const completed = Boolean(attempted) && axes.aurora === 'PERMITTED' && axes.evidence === 'RECEIPTED'
  const blocked = Boolean(attempted) && (axes.policy === 'DENY' || axes.aurora === 'DENIED')
  // The rail has three values. `refused` means the service declined to submit
  // an ungoverned write: nothing ran, so this is neither an outcome to verify
  // nor a policy denial, and it must not read as either.
  const refused = Boolean(attempted) && attempted?.rail === 'refused'
  const unresolved = !completed && !blocked && !refused && Boolean(attempted || review.executionTurnId)
  const actionState = deciding
    ? 'recording'
    : executing
      ? 'executing'
      : completed
        ? 'completed'
        : blocked
          ? 'blocked'
          : refused
            ? 'refused'
            : unresolved ? 'unknown' : review.humanState
  const actionStateLabel = deciding
    ? 'Recording decision'
    : executing
      ? 'Evaluating'
      : completed
        ? review.action === 'replace_damaged_item' ? 'Replacement reserved' : 'Completed'
        : blocked
          ? 'Not applied'
          : refused
            ? 'Not submitted'
          : unresolved
            ? 'Outcome unverified'
          : pending
            ? 'Decision required'
            : review.humanState === 'confirmed'
              ? 'Ready to execute'
              : 'Declined'
  const decisionActor =
    review.decidedBy && user?.sub === review.decidedBy
      ? 'you'
      : 'an authorized operator'
  const decisionTime = review.decidedAt
    ? new Date(review.decidedAt).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
    : null

  return (
    <div
      className="operator-review-record-layout"
      data-testid="operator-review-record"
    >
      <nav className="operator-back">
        <Link to="/operator/reviews">Action Queue</Link>
        <span aria-hidden="true">/</span>
        <span>{client.name}</span>
      </nav>
      <div className="operator-review-case-workspace">
      <div className="operator-review-context-stack">
      <div className="operator-review-overview">
        <p>{actionTitle(review.action, review.parameters)}</p>
        <a href="#operator-review-decision" className="pellier-action-quiet">Review decision</a>
      </div>

      {/* Origin, stated once and early. The issue is joined rather than interpolated
          because it is genuinely optional — a review prepared from an operator request
          may carry none — and a template left "Rachel Green ·" trailing a separator
          with nothing after it. */}
      <p
        className="operator-review-requester"
        data-testid="operator-review-requester"
        data-requester={review.requesterKind}
      >
        {requesterLine(review)}
      </p>
      <p className="operator-review-origin" data-testid="operator-review-origin">
        {['Prepared from Pellier', client.name, review.issue]
          .filter(Boolean)
          .join(' · ')}
      </p>

      {/* CUSTOMER */}
      <header className="operator-review-head" data-testid="operator-review-client">
        <ClientAvatar
          customerId={client.customerId}
          name={client.name}
          personaId={client.personaId}
        />
        <div>
          <h1 className="operator-title">{client.name}</h1>
          <p className="operator-review-standing">
            <MembershipRung membership={client.membership} />
            <span className="operator-ladder-descriptor">{rung.descriptor}</span>
            <span className="operator-figure-label">
              {money(client.spend12mo)} in 12 months
            </span>
          </p>
          <div className="operator-review-client-actions">
          <Link
            to={chatHref}
            className="operator-client-chat-link"
            data-testid="operator-review-chat-link"
          >
            {sourceSession ? 'Return to conversation' : 'Open client chat'}
          </Link>
          <Link
            to={`/operator/clients/${client.customerId}`}
            className="operator-filter-clear"
            data-testid="operator-review-client-link"
          >
            Open the full client record
          </Link>
          </div>
        </div>
      </header>

      {shopperHandoff ? (
        <div className="operator-card operator-review-handoff-card">
          <ShopperHandoffView handoff={shopperHandoff} clientName={client.name} />
        </div>
      ) : null}

      {/* ISSUE */}
      <section
        className="operator-card operator-review-context-card"
        data-testid="operator-review-issue"
      >
        <h2 className="operator-card-title">Issue</h2>
        <p className="operator-review-issue-text">
          {/* The issue describes the PROBLEM ("arrived damaged"), and the product name
              is prefixed to make a sentence of it. But `prepare_proposal` defaults the
              issue to the item name when the operator stated no problem, which rendered
              "Ivory Cashmere Throw Ivory Cashmere Throw". Prefix only when the issue is
              actually saying something else. */}
          {issueLine(product?.name, review.issue)}
        </p>
        {priorDamaged.length > 0 ? (
          <p className="operator-cell-note" data-testid="operator-review-prior">
            {/* The status belongs to the most recent one, so say which. Appending it
                bare to a count read as though every return shared that status. */}
            This client has {priorDamaged.length} previous damaged{' '}
            {priorDamaged.length === 1 ? 'return' : 'returns'} on record
            {priorDamaged[0]
              ? `, most recently ${priorDamaged[0].status}`
              : ''}
            . Worth weighing before a second courtesy remedy.
          </p>
        ) : null}
      </section>

      {/* ORDER */}
      <section
        className="operator-card operator-review-order-card"
        data-testid="operator-review-order"
      >
        <h2 className="operator-card-title">Order</h2>
        {order ? (
          <div className="operator-table-wrap" tabIndex={0} role="region" aria-label="Order details"><table className="operator-table">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Piece</th>
                <th scope="col">Placed</th>
                <th scope="col">Paid</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="operator-table-id">{order.orderId}</td>
                <td>
                  <div className="operator-review-order-piece">
                  {order.imageUrl ? <img src={imageSrc(order.imageUrl)} alt="" width={64} height={80} loading="lazy" /> : null}
                  <div>
                  {order.productName}
                  {/* A div, not a span: `operator-cell-note` carries no display
                      rule, so inline rendering ran the brand straight onto the
                      piece name — "Coral Lacquer CatchallPellier Maison". The
                      client record already stacks them this way. */}
                  <div className="operator-cell-note">{order.brand}</div>
                  </div>
                  </div>
                </td>
                <td>
                  {order.placedAt
                    ? new Date(order.placedAt).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })
                    : '—'}
                </td>
                <td>{money(order.price * order.quantity)}</td>
              </tr>
            </tbody>
          </table></div>
        ) : (
          <p className="operator-cell-note">
            No order row resolved for this review.
          </p>
        )}
        {/* pellier.orders carries no status column, so the honest lifecycle
            signal is the return record rather than an invented status. */}
        {returns.length > 0 ? (
          <p className="operator-cell-note" data-testid="operator-review-returns">
            Return history: {returns.length} on file, most recent{' '}
            {returns[0].reason.replace(/_/g, ' ')} ({returns[0].status}).
          </p>
        ) : (
          <p className="operator-cell-note">No returns on file for this client.</p>
        )}
      </section>

      {/* AGENT RECOMMENDATION */}
      <section
        className="operator-card operator-review-recommendation-card"
        data-testid="operator-review-recommendation"
      >
        <h2 className="operator-card-title">Pellier recommends</h2>
        <p className="operator-review-issue-text">
          {actionTitle(review.action, review.parameters)}
        </p>
        {review.recommendation.rationale ? (
          <p className="operator-cell-note">{review.recommendation.rationale}</p>
        ) : null}
        {/* Replacement availability is a live fact, resolved on this read. */}
        <p className="operator-cell-note" data-testid="operator-review-fulfilment">
          {fulfilment.availabilityVerified === false
            ? 'Replacement availability is not verified for this piece.'
            : fulfilment.replacementAvailable
              ? `A replacement is available: ${fulfilment.totalUnits} units across ${fulfilment.warehouses.length} warehouses.`
              : 'No replacement stock is available right now.'}
        </p>
        {review.recommendation.secondarySuggestion ? (
          <p
            className="operator-cell-note"
            data-testid="operator-review-secondary"
          >
            Optional:{' '}
            {review.recommendation.secondarySuggestion.action === 'issue_credit'
              ? `a courtesy credit of ${centsToMoney(
                  review.recommendation.secondarySuggestion.amountCents ?? 0,
                )}`
              : review.recommendation.secondarySuggestion.action}
            . {review.recommendation.secondarySuggestion.rationale ?? ''}
          </p>
        ) : null}
      </section>

      </div>
      <aside className="operator-review-decision-stack" aria-label="Proposed action and decision">
        <div className="operator-review-head-state" data-state={actionState}>
          <span className="operator-review-cell-label">Action state</span>
          <span>{actionStateLabel}</span>
        </div>
      {/* PROPOSED ACTION */}
      <section
        className="operator-card operator-review-action-card"
        data-testid="operator-review-action"
      >
        <h2 className="operator-card-title"><span className="operator-decision-step" aria-hidden="true">1</span>Proposed action</h2>
        <p className="operator-table-id operator-review-action-name">
          {review.action}
        </p>
        <div className="operator-table-wrap" tabIndex={0} role="region" aria-label="Exact action parameters"><table className="operator-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Value</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(review.parameters).map(([key, value]) => (
              <tr key={key} data-testid={`operator-review-param-${key}`}>
                <td>{PARAMETER_LABELS[key] ?? key}</td>
                <td className="operator-table-id">{formatParameter(key, value, order)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <p className="operator-cell-note">
          Confirming binds to exactly these values. Changed terms require a new
          confirmation.
        </p>
      </section>

      {/* HUMAN DECISION */}
      <section
        className="operator-card operator-review-decision-card"
        id="operator-review-decision"
        data-testid="operator-review-decision"
      >
        <h2 className="operator-card-title"><span className="operator-decision-step" aria-hidden="true">2</span>Your decision</h2>
        {deciding ? (
          <p
            className="operator-review-live-status"
            data-state="active"
            data-testid="operator-review-live-status"
            role="status"
          >
            <LoaderCircle className="operator-review-live-icon" aria-hidden />
            <span>
              <strong>Recording your decision</strong>
              PostgreSQL is persisting the decision before this page changes
              state.
            </span>
          </p>
        ) : executing ? (
          <p
            className="operator-review-live-status"
            data-state="active"
            data-testid="operator-review-live-status"
            role="status"
          >
            <LoaderCircle className="operator-review-live-icon" aria-hidden />
            <span>
              <strong>Evaluating the governed action</strong>
              The persisted action is entering its configured execution rail.
              The returned receipt will show whether AgentCore Policy evaluated
              it and whether Aurora was reached.
            </span>
          </p>
        ) : null}
        {pending ? (
          <>
            <div className="operator-review-actions">
              <button
                type="button"
                className="operator-button operator-button-inline"
                onClick={() => decide('confirm')}
                disabled={deciding || refreshNeeded || refreshing}
                data-testid="operator-review-confirm"
              >
                {deciding ? 'Recording…' : 'Confirm this action'}
              </button>
              <button
                type="button"
                className="operator-button operator-button-inline operator-button-quiet"
                onClick={() => decide('decline')}
                disabled={deciding || refreshNeeded || refreshing}
                data-testid="operator-review-decline"
              >
                Decline
              </button>
            </div>
            <p className="operator-cell-note">
              Confirming records your approval of these terms. Carrying the
              action out is a separate, authorized step.
            </p>
          </>
        ) : (
          <>
            <p
              className="operator-review-decision-summary"
              data-testid="operator-review-decided"
            >
              {review.humanState === 'confirmed' ? (
                <CheckCircle2
                  className="operator-review-decision-icon"
                  aria-hidden
                />
              ) : (
                <CircleX
                  className="operator-review-decision-icon"
                  aria-hidden
                />
              )}
              <span>
                <strong>
                  {review.humanState === 'confirmed' ? 'Confirmed' : 'Declined'}{' '}
                  by {decisionActor}
                </strong>
                {decisionTime ? <span>{decisionTime}</span> : null}
              </span>
            </p>
            {review.decidedBy || review.decidedAt ? (
              <details className="operator-review-audit-identity">
                <summary>Audit identity</summary>
                <dl>
                  {review.decidedBy ? (
                    <div>
                      <dt>Principal</dt>
                      <dd className="operator-receipt-key">
                        {review.decidedBy}
                      </dd>
                    </div>
                  ) : null}
                  {review.decidedAt ? (
                    <div>
                      <dt>Recorded</dt>
                      <dd className="operator-receipt-key">
                        {review.decidedAt}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </details>
            ) : null}
            {review.humanState === 'confirmed' && !attempted && !review.executionTurnId ? (
              <>
                <div className="operator-review-actions">
                  <button
                    type="button"
                    className="operator-button operator-button-inline"
                    onClick={execute}
                    disabled={executing || refreshNeeded || refreshing}
                    data-testid="operator-review-execute"
                  >
                    {executing ? 'Executing…' : 'Execute this action'}
                  </button>
                </div>
                <p className="operator-cell-note">
                  A person has approved these terms. Executing asks whether the
                  system is authorised to carry them out, which is a separate
                  question with its own answer.
                </p>
              </>
            ) : null}
            {attempted ? (
              <p
                className="operator-cell-note"
                data-testid="operator-review-execution"
              >
                {/* A denied action was never executed, so "Executed on the managed
                    Gateway rail" was false on every DENY — and the row-scope clause
                    was irrelevant, because nothing reached the database to be scoped.
                    Submitted is the honest verb for the attempt; executed is reserved
                    for the calls that entered the tool. */}
                {attempted.rail === 'refused' ? (
                  <>
                    <strong>Action not submitted.</strong>{' '}
                    The governed rail was unavailable, so the request never left
                    this service. Nothing ran, and there is no execution receipt
                    to read.
                  </>
                ) : axes.policy === 'DENY' ? (
                  <>
                    <strong>Action blocked.</strong>{' '}
                    Submitted on the{' '}
                    {attempted.rail === 'gateway-mcp'
                      ? 'managed Gateway rail'
                      : 'in-process rail'}
                    {' '}and refused before the tool was entered.
                  </>
                ) : (
                  <>
                    <strong>
                      {axes.evidence === 'RECEIPTED'
                        ? 'Action completed.'
                        : blocked ? 'Action not applied.' : 'Outcome unverified.'}
                    </strong>{' '}
                    Executed on the{' '}
                    {attempted.rail === 'gateway-mcp'
                      ? 'managed Gateway rail'
                      : 'in-process rail'}
                    {attempted.customerSubject
                      ? ', scoped to the client\u2019s own rows.'
                      : '. This client has no identity mapping, so no row scope was resolved.'}
                  </>
                )}
              </p>
            ) : null}
          </>
        )}
        {unresolved && !attempted ? <p role="status">Execution was requested. A durable outcome is not yet available; refresh the record to check it.</p> : null}
        {review.action === 'replace_damaged_item' ? <>
          <p className="operator-cell-note">This action records the return and reserves replacement stock. Fulfillment and shipment are recorded separately.</p>
          <Link className="operator-client-chat-link" to={`/operator/clients/${encodeURIComponent(review.customerId)}#operator-replacement-care`}>Check replacement care</Link>
          {review.humanState === 'confirmed' && unresolved && !refreshNeeded ? <div className="operator-review-actions">
            <button type="button" className="operator-button operator-button-inline" onClick={execute} disabled={executing || refreshing}>
              {executing ? 'Checking approved action…' : 'Recover this approved action'}
            </button>
            <p className="operator-cell-note">Uses the same approval and operation key. A committed result is replayed; if nothing committed, the approved terms are checked again before execution.</p>
          </div> : null}
        </> : null}
        {refreshNote ? <p role="status">{refreshNote}</p> : null}
        {refreshNeeded || unresolved ? <button type="button" className="operator-button operator-button-inline" disabled={refreshing} onClick={() => void reconcile()}>{refreshing ? 'Refreshing…' : 'Refresh record'}</button> : null}
        {decisionError ? (
          <p
            className="operator-receipt-key"
            data-testid="operator-review-decision-error"
          >
            {describeDecisionError(decisionError, decisionErrorMissing)}
          </p>
        ) : null}
      </section>
      </aside>
      </div>

      <ActionAssurance
        assurance={axes}
        phase={phase}
        /* The server's specific sentences — which policy matched, which client had
           no mapping — outrank the static ones, and they must survive a reload. The
           stored receipt carries the same two it returned. */
        notes={execution?.notes ?? review.execution?.notes}
        caption="Four separate questions. None of them answers another."
      />

      {/* What produced the verdicts above. The axes are a claim; this is its basis,
          and "Allow" without the engine and the mode cannot be told apart from an
          unenforced observation under LOG_ONLY. Rendered from the stored receipt, so
          it is here for anyone who opens the page later — not only for the operator
          who pressed the button. */}
      {review.execution ? (
        <section
          className="operator-receipt"
          data-testid="operator-review-receipt"
          data-mode={review.execution.gatewayMode || 'unknown'}
        >
          <h2 className="operator-card-title">What decided this</h2>
          <dl className="operator-receipt-rows">
            <div>
              <dt>Policy engine</dt>
              <dd className="operator-receipt-key">
                {review.execution.policyEngineId || 'None — this rail consults no engine'}
              </dd>
            </div>
            <div>
              <dt>Enforcement</dt>
              <dd>
                {review.execution.gatewayMode === 'ENFORCE'
                  ? 'ENFORCE — a denial would have been enforced'
                  : review.execution.gatewayMode === 'LOG_ONLY'
                    ? 'LOG_ONLY — decisions were observed, not enforced'
                    : 'Not recorded'}
              </dd>
            </div>
            <div>
              <dt>Action evaluated</dt>
              <dd className="operator-receipt-key">
                {review.execution.gatewayActionId}
              </dd>
            </div>
            {review.execution.matchingForbids.length ? (
              <div>
                {/* Named, not blamed. The same conditional forbid is listed beside an
                    ALLOW, where it means the rule was evaluated and did not apply. */}
                <dt>Forbid rules naming this action</dt>
                <dd className="operator-receipt-key">
                  {review.execution.matchingForbids.join(', ')}
                </dd>
              </div>
            ) : null}
            <div>
              <dt>Write key</dt>
              <dd className="operator-receipt-key">
                {review.execution.idempotencyKey}
              </dd>
            </div>
            {review.execution.recordedAt ? (
              <div>
                <dt>Recorded</dt>
                <dd>
                  {new Date(review.execution.recordedAt).toLocaleString('en-US')}
                </dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}

      {/* The evidence link, where the raw identifiers belong. */}
      {review.sourceTurnId ? (
        <p className="operator-review-proof-link">
          <Link
            className="pellier-action-quiet"
            to={`/observatory/operator-lineage?customer=${encodeURIComponent(
              review.customerId,
            )}&review=${encodeURIComponent(String(review.reviewId))}`}
            data-testid="operator-review-observatory-link"
          >
            Inspect this governed handoff in Pellier Observatory
          </Link>
        </p>
      ) : null}
    </div>
  )
}

const ReviewRecord: React.FC = () => {
  const { reviewId } = useParams()
  return <ReviewRecordPage key={reviewId} />
}

export default ReviewRecord
