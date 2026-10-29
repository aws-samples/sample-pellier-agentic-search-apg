/**
 * GovernedSeal — rail state, never decoration.
 *
 * The seal answers one question: did this turn actually travel the
 * governed rail? It is driven entirely by the `railDecision` the backend
 * attaches to a completed turn (`services/execution_rail.py`).
 *
 * The hard rule, and the reason this component exists rather than a static
 * badge in the header: **green "Governed" appears only for a verified
 * `gateway-mcp` rail.** A permanent green seal would be a brand ornament
 * that lies whenever provisioning is incomplete — which is exactly the
 * state most workshop boxes are in before Lab 4. Every other state gets
 * its own honest treatment:
 *
 *   verified    green   Gateway MCP confirmed under the caller's identity
 *   selected    neutral managed runtime chosen, Gateway not yet confirmed
 *   in-process  neutral ran locally; a legitimate rail, not a failure
 *   degraded    amber   governed rail requested but unavailable
 *   unknown     neutral no rail reported
 *
 * With no rail evidence at all the component renders nothing in `compact`
 * mode rather than guessing, so the Pellier header stays quiet until the
 * system has something true to say.
 */
import type React from 'react'
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  ShieldQuestion,
} from 'lucide-react'
import {
  RAIL_STATE_DETAIL,
  RAIL_STATE_LABEL,
  resolveRailState,
  type GovernedRailState,
  type RailDecision,
} from './governedTypes'

export interface GovernedSealProps {
  /** Rail decision from the completed turn. Absent = nothing verified. */
  railDecision?: RailDecision | null
  /**
   * `compact` renders a single chip for the header/hero.
   * `expanded` adds the explanatory line for evidence surfaces.
   */
  variant?: 'compact' | 'expanded'
  /** Render nothing when there is no rail evidence (default true). */
  hideWhenUnknown?: boolean
  className?: string
}

interface SealPresentation {
  Icon: typeof Shield
  fg: string
  bg: string
  border: string
}

const PRESENTATION: Record<GovernedRailState, SealPresentation> = {
  verified: {
    Icon: ShieldCheck,
    fg: 'var(--gov-rail-gateway-fg)',
    bg: 'var(--gov-rail-gateway-bg)',
    border: 'var(--gov-allow-border)',
  },
  selected: {
    Icon: Shield,
    fg: 'var(--gov-rail-inprocess-fg)',
    bg: 'var(--gov-rail-inprocess-bg)',
    border: 'var(--gov-neutral-border)',
  },
  'in-process': {
    Icon: Shield,
    fg: 'var(--gov-rail-inprocess-fg)',
    bg: 'var(--gov-rail-inprocess-bg)',
    border: 'var(--gov-neutral-border)',
  },
  refused: {
    Icon: ShieldOff,
    fg: 'var(--gov-deny-fg)',
    bg: 'var(--gov-deny-bg)',
    border: 'var(--gov-deny-border)',
  },
  degraded: {
    Icon: ShieldAlert,
    fg: 'var(--gov-rail-fallback-fg)',
    bg: 'var(--gov-rail-fallback-bg)',
    border: 'var(--gov-degraded-border)',
  },
  unknown: {
    Icon: ShieldQuestion,
    fg: 'var(--gov-unavailable-fg)',
    bg: 'var(--gov-unavailable-bg)',
    border: 'var(--gov-unavailable-border)',
  },
}

export const GovernedSeal: React.FC<GovernedSealProps> = ({
  railDecision,
  variant = 'compact',
  hideWhenUnknown = true,
  className,
}) => {
  const state = resolveRailState(railDecision)

  // No evidence: say nothing rather than imply something.
  if (state === 'unknown' && hideWhenUnknown && variant === 'compact') {
    return null
  }

  const p = PRESENTATION[state]
  const label = RAIL_STATE_LABEL[state]
  const detail = RAIL_STATE_DETAIL[state]
  const railName = railDecision?.rail ?? 'unreported'

  const chip = (
    <span
      data-testid="governed-seal"
      data-rail-state={state}
      data-rail={railName}
      title={detail}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'var(--dl-font-mono)',
        fontSize: '12px',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        fontWeight: 600,
        color: p.fg,
        backgroundColor: p.bg,
        border: `1px solid ${p.border}`,
        borderRadius: '999px',
        padding: '4px 10px',
        whiteSpace: 'nowrap',
      }}
    >
      <p.Icon size={13} aria-hidden="true" />
      <span aria-hidden="true">{label}</span>
      {/* The accessible name states the rail explicitly — a sighted user
          reads "GOVERNED", a screen-reader user hears which rail earned it. */}
      <span className="gov-visually-hidden">
        {`Execution rail: ${label} (${railName}). ${detail}`}
      </span>
    </span>
  )

  if (variant === 'compact') return <span className={className}>{chip}</span>

  return (
    <div
      className={className}
      style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}
    >
      {chip}
      <p
        style={{
          fontFamily: 'var(--dl-font-sans)',
          fontSize: '14px',
          lineHeight: 1.55,
          color: 'var(--dl-ink-2)',
          margin: 0,
        }}
      >
        {detail}
      </p>
      {railDecision?.managedRequested && !railDecision.available && (
        <p
          style={{
            fontFamily: 'var(--dl-font-mono)',
            fontSize: '12px',
            color: 'var(--gov-degraded-fg)',
            margin: 0,
          }}
        >
          reason: {railDecision.reason ?? 'unspecified'}
        </p>
      )}
    </div>
  )
}

export default GovernedSeal
