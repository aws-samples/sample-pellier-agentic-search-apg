/**
 * What the desk says when it has nothing to show, or cannot show it.
 *
 * One shape for every absence: which panel is empty, one sentence in the
 * desk's heading voice, what would fill it, and at most one action. The
 * signed-out desk is the first thing a participant sees, so it must read as
 * the desk working exactly as designed, not as a rendering failure.
 */
import type React from 'react'

export interface OperatorStateProps {
  /** Names the panel that is empty, unreachable, or still loading. */
  eyebrow: string
  /** One sentence. Say what is absent, not "no data". */
  headline: React.ReactNode
  /** What would put something here, or which boundary was hit. */
  body?: React.ReactNode
  /** The identifier an operator can go and check. Rendered in mono. */
  reason?: React.ReactNode
  /** At most one recovery action. */
  action?: React.ReactNode
  /** Heading rank for the headline. `1` when this state replaces the page. */
  level?: 1 | 2 | 3
  /** A quiet pulse while the desk reads. */
  busy?: boolean
  'data-testid': string
}

const OperatorState: React.FC<OperatorStateProps> = ({
  eyebrow, headline, body, reason, action, level = 2, busy = false, 'data-testid': testId,
}) => {
  const Heading = `h${level}` as 'h1' | 'h2' | 'h3'
  return (
    <div className="op-state" data-busy={busy ? 'true' : 'false'} data-testid={testId}>
      <p className="op-eyebrow">{eyebrow}</p>
      <Heading className="op-state-headline">
        {busy ? <span className="tn-dot" aria-hidden="true" /> : null}
        {headline}
      </Heading>
      {body ? <p className="op-state-body">{body}</p> : null}
      {reason ? <code className="op-state-reason">{reason}</code> : null}
      {action ? <div className="op-state-action">{action}</div> : null}
    </div>
  )
}

export default OperatorState

/** The desk's three ways of being locked, in one place. */
export function describeOperatorError(error: string, what: string): { headline: string; body: string; signIn: boolean } {
  if (error === 'authentication_required' || error === 'invalid_credentials' || error === 'operator_sign_in_required') {
    return {
      headline: 'Staff sign-in required',
      body: `Sign in as Nadia with her password to ${what}. No database request was attempted.`,
      signIn: true,
    }
  }
  if (error === 'operator_group_required') {
    return {
      headline: 'Staff access required',
      body: 'This signed-in account is not in the operator group, so the desk refused it. No database request was attempted.',
      signIn: false,
    }
  }
  if (error === 'operator_unavailable') {
    return {
      headline: 'The desk is temporarily unavailable',
      body: `The service could not be reached, so it could not ${what}.`,
      signIn: false,
    }
  }
  return {
    headline: 'Unavailable',
    body: `The database did not return what the desk needs to ${what}.`,
    signIn: false,
  }
}
