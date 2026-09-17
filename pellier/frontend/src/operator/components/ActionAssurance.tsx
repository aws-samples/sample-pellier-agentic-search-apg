/**
 * The four assurance axes, rendered as four independent states.
 *
 * This is a semantic component, not Theo's copy. Every governed action in the
 * console answers the same four questions, and they must be answerable
 * separately:
 *
 *   Human    did a person decide?
 *   Policy   was the action authorized?
 *   Aurora   did the database let it through?
 *   Evidence what proves it ran?
 *
 * The whole point is that these do not follow from one another. A person saying
 * yes is not an authorization; an authorization is not a database effect; a
 * database effect is not evidence until something durable records it. A single
 * `governed: true` badge would collapse all four into a claim none of them
 * individually supports, so the states arrive from the API and are printed
 * verbatim.
 *
 * States are carried by a label and a data attribute, never by colour alone.
 */

import { LoaderCircle } from 'lucide-react'
import React from 'react'
import type { ActionAssurance as Assurance } from '../../services/operator'

/** Display copy per raw state. Absent keys render the raw token rather than
 *  guessing, so an unrecognised state is visible instead of silently pretty. */
const STATE_LABELS: Record<string, string> = {
  CONFIRMATION_REQUIRED: 'Confirmation required',
  CONFIRMED: 'Confirmed',
  DECLINED: 'Declined',
  PENDING: 'Pending',
  NOT_EVALUATED: 'Not evaluated',
  NOT_REACHED: 'Not reached',
  OUTCOME_UNKNOWN: 'Outcome needs checking',
  NO_EXECUTION: 'No execution',
  ALLOW: 'Allow',
  DENY: 'Deny',
  WOULD_DENY: 'Would deny',
  EVALUATION_INCOMPLETE: 'Evaluation incomplete',
  POLICY_INFERRED: 'Inferred from policy text',
  PERMITTED: 'Permitted',
  DENIED: 'Denied',
  NOT_ENFORCED: 'Not enforced',
  RECEIPTED: 'Receipted',
  POLICY_PROOF: 'Policy proof',
  ATTEMPT_RECEIPT: 'Attempt receipt',
}

/** Why each axis is in this state, in one line an operator can act on. */
const AXIS_NOTES: Record<keyof Assurance, Record<string, string>> = {
  human: {
    CONFIRMATION_REQUIRED: 'Pellier prepared this request and stopped.',
    CONFIRMED: 'A person approved this exact action.',
    DECLINED: 'A person refused. Nothing was submitted.',
  },
  policy: {
    PENDING: 'Nothing has been submitted for authorization yet.',
    NOT_EVALUATED: 'No policy engine was asked.',
    ALLOW: 'AgentCore Policy evaluated this action and permitted it.',
    DENY: 'AgentCore Policy refused. The tool was never entered.',
    WOULD_DENY: 'A forbid policy matched, but enforcement is off. Observed, not enforced.',
    EVALUATION_INCOMPLETE:
      'The engine was asked and its decision could not be read. This is not an ALLOW.',
    POLICY_INFERRED:
      'Inferred from policy text, not a decision. No engine evaluated this action.',
  },
  aurora: {
    OUTCOME_UNKNOWN: 'The response does not establish the commit outcome. Read the durable record for the same operation key before deciding what happened.',
    NOT_EVALUATED: 'No statement has reached the database.',
    NOT_REACHED: 'The database was never asked to change anything.',
    PERMITTED: 'Row-Level Security was in scope and the transaction committed.',
    DENIED: 'The database refused the statement. Nothing changed.',
    NOT_ENFORCED: 'This rail did not bind a row-scoped role, so RLS did not apply.',
  },
  evidence: {
    PENDING: 'No durable execution receipt is available yet.',
    NO_EXECUTION: 'Nothing ran, so there is no receipt. That is the proof.',
    RECEIPTED: 'A durable write event and an execution receipt exist.',
    POLICY_PROOF: 'The policy decision is the artifact; there is no tool receipt.',
    ATTEMPT_RECEIPT: 'An execution attempt was recorded. Read the Aurora outcome separately.',
  },
}

const AXES: { key: keyof Assurance; label: string }[] = [
  { key: 'human', label: 'Human' },
  { key: 'policy', label: 'AgentCore Policy' },
  { key: 'aurora', label: 'Aurora' },
  { key: 'evidence', label: 'Evidence' },
]

interface Props {
  assurance: Assurance
  /** Optional caption. Keep it short; the axes carry the meaning. */
  caption?: string
  /**
   * Server-supplied reasons, which override the static ones where present.
   * The server knows which policy matched and which client had no mapping; a
   * generic sentence here would be less true than the specific one it sends.
   */
  notes?: Partial<Record<keyof Assurance, string>>
  /** A real in-flight request boundary, never a simulated progression. */
  phase?: 'recording_decision' | 'executing'
}

const LIVE_STATES: Record<
  NonNullable<Props['phase']>,
  Partial<Record<keyof Assurance, { label: string; note: string }>>
> = {
  recording_decision: {
    human: {
      label: 'Recording decision',
      note: 'PostgreSQL is persisting the operator decision.',
    },
  },
  executing: {
    policy: {
      label: 'Resolving rail',
      note: 'The response will state whether AgentCore Policy evaluated the action.',
    },
    aurora: {
      label: 'Waiting on rail',
      note: 'Aurora is reached only if the configured execution rail enters the tool.',
    },
    evidence: {
      label: 'Awaiting result',
      note: 'The attempt is incomplete until its durable receipt can be read.',
    },
  },
}

const ActionAssurance: React.FC<Props> = ({
  assurance,
  caption,
  notes,
  phase,
}) => (
  <section className="operator-assurance" data-testid="operator-assurance">
    <h2 className="operator-card-title">Action assurance</h2>
    {caption ? <p className="operator-assurance-caption">{caption}</p> : null}
    <dl className="operator-assurance-grid">
      {AXES.map(({ key, label }) => {
        const state = assurance[key]
        const live = phase ? LIVE_STATES[phase][key] : undefined
        return (
          <div
            className="operator-assurance-axis"
            key={key}
            data-axis={key}
            data-state={state}
            data-live-state={live ? 'active' : undefined}
            data-testid={`operator-assurance-${key}`}
          >
            <dt className="operator-assurance-label">{label}</dt>
            <dd className="operator-assurance-state">
              {live ? (
                <span className="operator-assurance-live-label">
                  <LoaderCircle
                    className="operator-assurance-spinner"
                    aria-hidden
                  />
                  {live.label}
                </span>
              ) : (
                STATE_LABELS[state] ?? state
              )}
              <span className="operator-assurance-note">
                {live?.note ?? notes?.[key] ?? AXIS_NOTES[key][state] ?? ''}
              </span>
            </dd>
          </div>
        )
      })}
    </dl>
  </section>
)

export default ActionAssurance
