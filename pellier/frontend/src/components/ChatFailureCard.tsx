import {
  AlertCircle,
  Clock3,
  KeyRound,
  LogIn,
  Pencil,
  RotateCcw,
  ShieldCheck,
  WifiOff,
} from 'lucide-react'
import type { ChatFailure } from '../hooks/useAgentChat'
import type { ChatErrorCode } from '../services/chat'
import { CHAT_FAILURES } from '../copy'
import '../styles/chat-outcomes.css'

/** Where an expired-session "Sign in again" stands, so the card can show it. */
export interface ReauthState {
  /** The request being sent again once the shopper is signed in. */
  query: string | null
  /** The shopper is being signed in again. */
  pending: boolean
  /** The last attempt did not complete. */
  failed: boolean
  /** What makes signing in again wait: a running reply or a shopper switch. */
  blockedBy: 'reply' | 'switch' | null
}

interface ChatFailureCardProps {
  failure: ChatFailure
  onRetry: (query: string) => void
  onEditRequest: (query: string) => void
  onAuthenticate: (query: string) => void
  reauth?: ReauthState
}

function failureIcon(code: ChatErrorCode) {
  if (code === 'policy_denied') return ShieldCheck
  if (code === 'authentication_required') return KeyRound
  if (code === 'request_timeout' || code === 'rate_limited') return Clock3
  if (code === 'network_error' || code === 'service_unavailable') return WifiOff
  return AlertCircle
}

export default function ChatFailureCard({
  failure,
  onRetry,
  onEditRequest,
  onAuthenticate,
  reauth,
}: ChatFailureCardProps) {
  const copy = CHAT_FAILURES[failure.code]
  const FailureIcon = failureIcon(failure.code)
  const mine = reauth?.query === failure.query
  const pending = Boolean(mine && reauth?.pending)
  const failed = Boolean(mine && reauth?.failed)

  return (
    <div
      className={[
        'chat-failure',
        `chat-failure--${failure.code}`,
      ].join(' ')}
      data-testid={`chat-failure-${failure.code}`}
      role="alert"
      aria-live="polite"
    >
      <div className="chat-failure__icon" aria-hidden="true">
        <FailureIcon size={18} />
      </div>
      <div className="chat-failure__content">
        <div className="chat-failure__eyebrow">{copy.eyebrow}</div>
        <h4>{copy.title}</h4>
        <p>{copy.body}</p>
        {failure.referenceId && (
          <p className="chat-failure__reference">
            Reference <code>{failure.referenceId}</code>
          </p>
        )}
        {failure.code === 'authentication_required' && !pending && (
          failed
            ? <p className="chat-failure__note" role="status">{CHAT_FAILURES.SIGN_IN_AGAIN_FAILED}</p>
            : reauth?.blockedBy === 'reply' && <p className="chat-failure__note">{CHAT_FAILURES.SIGN_IN_AGAIN_WAIT}</p>
        )}
        <div className="chat-failure__actions">
          {failure.code === 'authentication_required' ? (
            <button
              type="button"
              disabled={pending || Boolean(reauth?.blockedBy)}
              aria-busy={pending || undefined}
              onClick={() => onAuthenticate(failure.query)}
            >
              <LogIn size={14} aria-hidden="true" />
              {pending ? CHAT_FAILURES.SIGNING_IN_AGAIN : CHAT_FAILURES.SIGN_IN_AGAIN}
            </button>
          ) : failure.retryable ? (
            <button type="button" onClick={() => onRetry(failure.query)}>
              <RotateCcw size={14} aria-hidden="true" />
              {CHAT_FAILURES.TRY_AGAIN}
            </button>
          ) : null}
          <button
            type="button"
            className="chat-failure__action--secondary"
            onClick={() => onEditRequest(failure.query)}
          >
            <Pencil size={14} aria-hidden="true" />
            {CHAT_FAILURES.EDIT_REQUEST}
          </button>
        </div>
      </div>
    </div>
  )
}
