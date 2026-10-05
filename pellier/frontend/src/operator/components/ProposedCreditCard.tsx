/**
 * The proposed store credit, its three checks, and the decisions a person takes.
 *
 * The three checks answer three separate questions, and none of them answers
 * another:
 *
 *   Approval   did a person agree to exactly this credit?
 *   Policy     did AgentCore Policy permit the action?
 *   Recorded   what do the two tables hold for this write key?
 *
 * Every value comes from the API: the decision from the review row, the
 * policy verdict from the execute response or, after a reload, the answer the
 * Gateway gave the desk as stored on the review, and the counts from
 * `store_credits` and `tool_audit`, read from the tables.
 * A person saying yes is not an authorization, and an authorization is not a
 * row.
 */
import { CheckCircle2, CircleX, LoaderCircle } from 'lucide-react'
import React from 'react'
import { StatusTag, type TagTone } from '../../components/turn'
import type { ExecutionRecord, OperatorReview } from '../../services/operator'
import type { ReviewController } from '../hooks/useReview'
import ClientAvatar from './ClientAvatar'

/** Plain-language decision failure; the raw code stays visible for the receipt. */
const DECISION_ERROR_COPY: Record<string, string> = {
  parameters_changed: 'The proposed values changed since this page loaded. Reload and read the new terms before approving.',
  operator_sign_in_required: 'A staff sign-in is required to decide this credit.',
  authentication_required: 'Your staff sign-in has expired. Sign in again to decide this credit.',
  operator_group_required: 'This signed-in account is not in the operator group, so it cannot decide this credit.',
  review_not_found: 'This proposal no longer exists. Return to the reviews for the current list.',
  review_already_decided: 'This credit already has a decision. The record below is the current one.',
  operator_unavailable: 'The service response was unavailable. The record was re-read; check it before continuing.',
  governed_rail_unavailable: 'The governed rail is not available, so nothing was submitted and nothing ran. Restore the managed deployment before trying again.',
  investigation_failed: 'The investigation did not complete.',
}

export function describeDecisionError(code: string, missing: readonly string[] = []): string {
  const base = DECISION_ERROR_COPY[code] ?? `The outcome could not be verified (${code}). The record was re-read.`
  return missing.length ? `${base} Missing: ${missing.join(', ')}.` : base
}

/** The staff member whose portrait the desk has. */
const STAFF_PORTRAIT = 'nadia'

/** Present a bare Cognito username with a capital: `nadia` -> `Nadia`. */
export function presentIdentity(value: string | undefined | null): string {
  const text = String(value || '').trim()
  if (!text) return 'staff'
  if (!/^[a-z][a-z0-9._-]*$/.test(text)) return text
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The Lab 4 policy check's over-limit probe, as the desk names it. */
export const POLICY_CHECK_PROBE_LINE = 'Opened and confirmed by the Lab 4 policy check (probe data, covers no order)'

interface Check {
  key: 'approval' | 'policy' | 'recorded'
  label: string
  tone: TagTone
  tag: string
  pulse?: boolean
  detail: string
}

function approvalCheck(review: OperatorReview, decider: string): Check {
  if (review.policyCheckProbe) {
    return {
      key: 'approval', label: 'Approval', tone: 'pending', tag: 'No person approved it',
      detail: `${POLICY_CHECK_PROBE_LINE}. It exists to send one over-limit credit to Cedar.`,
    }
  }
  if (review.humanState === 'confirmed') {
    return {
      key: 'approval', label: 'Approval', tone: 'good', tag: `Approved by ${decider}`,
      detail: 'A person agreed to exactly this customer, amount and reason. Changed terms would need a new approval.',
    }
  }
  if (review.humanState === 'declined') {
    return {
      key: 'approval', label: 'Approval', tone: 'blocked', tag: `Declined by ${decider}`,
      detail: 'A person refused. Nothing was submitted anywhere.',
    }
  }
  return {
    key: 'approval', label: 'Approval', tone: 'pending', tag: 'Waiting for Nadia', pulse: true,
    detail: 'The Planner proposed this credit and stopped. Nothing changes until a person approves it.',
  }
}

function policyCheck(review: OperatorReview, attempted: boolean): Check {
  const { policy } = review.assurance
  if (!attempted || policy === 'PENDING') {
    return { key: 'policy', label: 'Policy', tone: 'pending', tag: 'Not evaluated yet',
             detail: 'Cedar is asked only when the approved credit is executed through the Gateway.' }
  }
  if (policy === 'ALLOW') {
    return { key: 'policy', label: 'Policy', tone: 'good', tag: 'ALLOW',
             detail: review.execution?.notes.policy ?? 'AgentCore Policy evaluated the action and permitted it.' }
  }
  if (policy === 'DENY') {
    return { key: 'policy', label: 'Policy', tone: 'blocked', tag: 'DENY',
             detail: review.execution?.notes.policy ?? 'AgentCore Policy refused the action. The tool was never entered.' }
  }
  if (policy === 'NOT_RECORDED') {
    return { key: 'policy', label: 'Policy', tone: 'pending', tag: 'Not stored',
             detail: review.execution?.notes.policy ?? 'No answer from the Gateway is stored for this attempt.' }
  }
  if (policy === 'NOT_EVALUATED') {
    return { key: 'policy', label: 'Policy', tone: 'pending', tag: 'Not evaluated',
             detail: review.execution?.notes.policy ?? 'This execution ran in process, so no policy engine was asked.' }
  }
  return { key: 'policy', label: 'Policy', tone: 'blocked', tag: 'Not readable',
           detail: review.execution?.notes.policy ?? 'The engine was asked and its decision could not be read. This is not an ALLOW.' }
}

function recordedCheck(record: ExecutionRecord | null, attempted: boolean, policy: string): Check {
  if (!attempted || !record) {
    return { key: 'recorded', label: 'Recorded', tone: 'pending', tag: 'Nothing written',
             detail: 'An executed credit leaves exactly one store_credits row and one tool_audit row for its key.' }
  }
  if (!record.readable) {
    return { key: 'recorded', label: 'Recorded', tone: 'pending', tag: 'Not readable',
             detail: 'The tables could not be read, so no count is claimed.' }
  }
  const credits = record.creditRows
  const audits = record.auditRows
  if (credits === 1 && audits === 1) {
    return {
      key: 'recorded', label: 'Recorded', tone: 'good', tag: 'Recorded once',
      detail: `Credit #${record.creditIds[0]} and tool_audit row #${record.auditIds[0]}, both once for this key. A retry keeps both at one.`,
    }
  }
  if (credits === 0 && audits === 0) {
    return {
      key: 'recorded', label: 'Recorded', tone: 'blocked', tag: 'Not written',
      detail: policy === 'DENY'
        ? 'Zero store_credits rows and zero tool_audit rows for this key: the tool was never entered.'
        : 'Zero store_credits rows and zero tool_audit rows for this key.',
    }
  }
  return {
    key: 'recorded', label: 'Recorded', tone: credits === 1 ? 'good' : 'blocked',
    tag: `${credits} credit row${credits === 1 ? '' : 's'}, ${audits} audit row${audits === 1 ? '' : 's'}`,
    detail: credits === 0
      ? 'The tool was entered and refused; the attempt is on the ledger and no credit was written.'
      : 'The counts for this key, read from the tables.',
  }
}

interface Props {
  controller: ReviewController
  /** The items the credit covers, when the record has them to show. */
  items?: string[]
  /** `compact` for the investigation column; the review record shows every line. */
  compact?: boolean
}

const ProposedCreditCard: React.FC<Props> = ({ controller, items, compact = false }) => {
  const { detail, busy, execution, decisionError, decisionErrorMissing, approve, decline, execute } = controller
  if (!detail) return null
  const { review, record: storedRecord } = detail
  const record = execution?.record ?? storedRecord
  const attempted = Boolean(execution || review.execution)
  const axes = execution ? execution.assurance : review.assurance
  const policy = execution ? axes.policy : review.assurance.policy
  // The decider the review recorded, the same for every staff member reading it.
  const decider = presentIdentity(review.decidedByName)
  const checks: Check[] = [
    approvalCheck(review, decider),
    policyCheck({ ...review, assurance: axes }, attempted),
    recordedCheck(record, attempted, policy),
  ]
  const pending = review.humanState === 'confirmation_required'
  // The Lab 4 check's probe is probe data: the desk never executes it.
  const approved = review.humanState === 'confirmed' && !review.policyCheckProbe
  const executed = Boolean(record && record.readable && record.creditRows === 1)
  const named = items ?? review.recommendation.items ?? []
  const deciderPortrait = !review.policyCheckProbe && (review.decidedByName || '').toLowerCase() === STAFF_PORTRAIT
    ? STAFF_PORTRAIT : null

  return (
    <section className="op-credit" data-state={review.humanState} data-testid="operator-proposed-credit">
      <header className="op-credit-head">
        <p className="op-eyebrow">Proposed store credit</p>
        <p className="op-credit-amount" data-testid="operator-credit-amount">${review.amount}</p>
        <p className="op-credit-reason">{review.reason}</p>
        {named.length > 0 ? (
          <p className="op-credit-items">For {named.join(' and ')}, for {review.customerName}.</p>
        ) : null}
      </header>

      <ol className="op-checks" data-testid="operator-credit-checks">
        {checks.map(check => (
          <li key={check.key} className="op-check" data-check={check.key} data-tone={check.tone}>
            <span className="op-check-label">{check.label}</span>
            <span className="op-check-tag">
              {check.key === 'approval' && deciderPortrait && review.humanState !== 'confirmation_required' ? (
                <ClientAvatar personaId={deciderPortrait} name={decider} />
              ) : null}
              <StatusTag tone={check.tone} pulse={check.pulse}>{check.tag}</StatusTag>
            </span>
            {!compact || check.tone !== 'pending' ? <span className="op-check-detail">{check.detail}</span> : null}
          </li>
        ))}
      </ol>

      {busy ? (
        <p className="op-live" role="status" data-testid="operator-credit-live">
          <LoaderCircle className="op-live-icon" aria-hidden />
          {busy === 'approving' ? 'Recording the approval' : busy === 'declining' ? 'Recording the decision' : 'Executing the approved credit'}
        </p>
      ) : null}

      <div className="op-credit-actions">
        {pending ? (
          <>
            <button type="button" className="op-button" onClick={() => void approve()} disabled={Boolean(busy)} data-testid="operator-review-confirm">
              Approve
            </button>
            <button type="button" className="op-button op-button-quiet" onClick={() => void decline()} disabled={Boolean(busy)} data-testid="operator-review-decline">
              Decline
            </button>
          </>
        ) : null}
        {approved && !executed ? (
          <button type="button" className="op-button" onClick={() => void execute()} disabled={Boolean(busy)} data-testid="operator-review-execute">
            {attempted ? 'Execute again' : 'Execute'}
          </button>
        ) : null}
        {approved && executed ? (
          <button type="button" className="op-button op-button-quiet" onClick={() => void execute()} disabled={Boolean(busy)} data-testid="operator-review-retry">
            Retry execution
          </button>
        ) : null}
      </div>

      {approved && !attempted ? (
        <p className="op-note">A person approved these terms. Executing asks whether the system may carry them out.</p>
      ) : null}
      {attempted && record?.readable && executed ? (
        <p className="op-note op-note-good" data-testid="operator-credit-recorded">
          <CheckCircle2 size={14} aria-hidden />
          Credit #{record.creditIds[0]} recorded for {review.customerName}.
          {execution?.result?.idempotent_replay ? ' This run replayed the existing credit; nothing was written twice.' : ''}
        </p>
      ) : null}
      {attempted && axes.policy === 'DENY' ? (
        <p className="op-note op-note-blocked" data-testid="operator-credit-denied">
          <CircleX size={14} aria-hidden />
          AgentCore Policy denied the credit before the tool ran. Nothing was written.
        </p>
      ) : null}
      {!compact ? (
        <dl className="op-key">
          <div>
            <dt>Write key</dt>
            <dd>{execution?.idempotencyKey ?? review.execution?.idempotencyKey ?? `operator-review:${review.reviewId}:${review.actionHash.slice(0, 32)}`}</dd>
          </div>
          <div>
            <dt>Rail</dt>
            <dd>{execution?.rail ?? (review.execution ? review.execution.rail ?? 'no row written' : 'not yet run')}</dd>
          </div>
        </dl>
      ) : null}
      {decisionError ? (
        <p className="op-error" data-testid="operator-review-decision-error">
          {describeDecisionError(decisionError, decisionErrorMissing)}
        </p>
      ) : null}
    </section>
  )
}

export default ProposedCreditCard
