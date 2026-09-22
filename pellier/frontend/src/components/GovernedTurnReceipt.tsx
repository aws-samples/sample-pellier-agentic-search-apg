import { apiFetch } from '../services/apiBase'
/**
 * GovernedTurnReceipt — the compact receipt under a completed answer.
 *
 * Design stance: quiet governance in Pellier. The shopper gets a beautiful
 * answer; the receipt is a single restrained line that says what the system
 * actually did, with the full accounting one click away in Observatory.
 *
 * The hard rule is **only render what the turn emitted**. Every field here
 * is optional, and an absent field renders as an honest "not reported"
 * rather than a zero. Inferring "0 sources" from a missing field would be a
 * fabricated claim about retrieval, and inferring a policy outcome from
 * silence would be worse — this workshop's entire point is that ALLOW,
 * DENY, and not-evaluated are three different things.
 *
 * Named `GovernedTurnReceipt` rather than `TurnReceipt` because
 * `components/TurnReceipt.tsx` already exists as the copy-reference chip.
 * Two components with one name in different namespaces is how a codebase
 * ends up with two divergent evidence models.
 */
import {
  useEffect,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { Link } from 'react-router-dom'
import { Database, Wrench } from 'lucide-react'
import { useOptionalAuth } from '../contexts/AuthContext'
import {
  GovernedSeal,
  PolicyDecisionBadge,
  receiptRoute,
  type PolicyDecision,
  type RailDecision,
} from '../shared'

export interface GovernedTurnReceiptProps {
  /** Session the turn belongs to; drives the evidence deep link. */
  sessionId?: string | null
  /** Stable per-turn id from the backend, when emitted. */
  turnId?: string | null
  /** Rail decision, used for the seal. */
  railDecision?: RailDecision | null
  /** Test-only injection; production always reads the authenticated API. */
  receipt?: PersistedGovernedTurnReceipt | null
}

export interface PersistedGovernedTurnReceipt {
  turn_id: string
  rail: string
  citations: Array<{
    evidence_id: string
    source_uri: string
    revision: string | null
    quote: string
    entity_id: string
  }>
  tool_audit_ids: Array<{
    audit_id: number
    tool: string
    caller: string
    latency_ms: number | null
    created_at: string | null
  }>
  policy_events: Array<{
    decision: PolicyDecision
    reason?: string | null
  }>
  terminal_status: string
  latency_ms: number | null
}

const labelStyle: CSSProperties = {
  fontFamily: 'var(--dl-font-mono)',
  fontSize: '10.5px',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'var(--dl-muted)',
}

const valueStyle: CSSProperties = {
  fontFamily: 'var(--dl-font-sans)',
  fontSize: '13px',
  color: 'var(--dl-ink)',
  fontWeight: 500,
}

/** One metric cell. Renders "not reported" when the turn emitted nothing. */
const Metric: React.FC<{
  icon: ReactNode
  label: string
  value: number | null | undefined
  suffix?: string
}> = ({ icon, label, value, suffix }) => {
  const known = typeof value === 'number' && Number.isFinite(value)
  return (
    <span
      style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
      title={known ? undefined : `${label} was not reported for this turn`}
    >
      <span aria-hidden="true" style={{ color: 'var(--dl-muted)', display: 'flex' }}>
        {icon}
      </span>
      <span style={labelStyle}>{label}</span>
      {known ? (
        <span style={valueStyle}>
          {value}
          {suffix ?? ''}
        </span>
      ) : (
        <span
          style={{ ...valueStyle, color: 'var(--gov-unavailable-fg)', fontWeight: 400 }}
        >
          not reported
        </span>
      )}
    </span>
  )
}

export const GovernedTurnReceipt: React.FC<GovernedTurnReceiptProps> = ({
  sessionId,
  turnId,
  railDecision,
  receipt: suppliedReceipt,
}) => {
  const isAuthenticated = useOptionalAuth()?.isAuthenticated ?? false
  const [loadedReceipt, setLoadedReceipt] =
    useState<PersistedGovernedTurnReceipt | null>(suppliedReceipt ?? null)

  useEffect(() => {
    if (suppliedReceipt) {
      setLoadedReceipt(suppliedReceipt)
      return
    }
    // The receipts API is authenticated; an anonymous shopper cannot have a
    // persisted receipt, so fetching would only manufacture a 401.
    if (!turnId || !isAuthenticated) {
      setLoadedReceipt(null)
      return
    }
    let active = true
    const controller = new AbortController()
    apiFetch(`/api/governed-receipts/${encodeURIComponent(turnId)}`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: PersistedGovernedTurnReceipt | null) => {
        if (active) setLoadedReceipt(data)
      })
      .catch(() => {
        if (active) setLoadedReceipt(null)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [suppliedReceipt, turnId, isAuthenticated])

  // No record means no claim. In particular, do not substitute product cards,
  // local tool chips, or a fixture when receipt persistence or authorization
  // did not produce an authenticated durable record.
  if (!loadedReceipt) return null

  const policy = loadedReceipt.policy_events[0]
  const policyDecision = policy?.decision
  const policyReason = policy?.reason
  const sourceCount = loadedReceipt.citations.length
  const toolCount = loadedReceipt.tool_audit_ids.length
  const latencyMs = loadedReceipt.latency_ms

  return (
    <div
      data-testid="governed-turn-receipt"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '14px',
        padding: '10px 12px',
        marginTop: '8px',
        background: 'var(--gov-surface-evidence)',
        border: `1px solid ${'var(--gov-hairline)'}`,
        borderRadius: 'var(--gov-radius-md)',
      }}
    >
      <Metric
        icon={<Database size={13} />}
        label="Sources"
        value={sourceCount ?? null}
      />
      <Metric icon={<Wrench size={13} />} label="Tools" value={toolCount ?? null} />

      {/* Policy is shown only when a decision exists. Absence is not ALLOW. */}
      {policyDecision && (
        <PolicyDecisionBadge decision={policyDecision} reason={policyReason} />
      )}

      {typeof latencyMs === 'number' && Number.isFinite(latencyMs) && (
        <Metric
          icon={<span style={{ fontSize: '11px' }}>⏱</span>}
          label="Latency"
          value={Math.round(latencyMs)}
          suffix="ms"
        />
      )}

      {railDecision && <GovernedSeal railDecision={railDecision} />}

      <span style={{ flex: 1 }} />

      {/* Base-path-safe: <Link> applies the router basename, so this works
          behind the Workshop Studio /ports/8000/ proxy. */}
      <Link
        to={receiptRoute({ sessionId, turnId })}
        className="pellier-action-quiet gov-focusable"
        data-testid="governed-receipt-link"
      >
        Why this answer?
      </Link>
    </div>
  )
}

export default GovernedTurnReceipt
