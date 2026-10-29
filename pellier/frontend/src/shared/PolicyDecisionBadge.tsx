/**
 * PolicyDecisionBadge — a Cedar decision, rendered asymmetrically.
 *
 * The asymmetry is the point. ALLOW and DENY must differ by icon, by text,
 * and by accessible name — never by color alone. Two badges that differ
 * only in hue are unreadable to a colorblind attendee and invisible in a
 * grayscale conference projection, which is precisely where this workshop
 * gets demonstrated.
 *
 * The three states carry different claims:
 *
 *   ALLOW                 the policy permitted the action; execution is a
 *                         separate fact
 *   DENY                  the policy blocked it *before* execution, no tool ran
 *   WOULD_DENY            a real deny event under LOG_ONLY: observed, not
 *                         enforced, so the tool did run
 *   NOT_EVALUATED         no policy decision exists for this turn
 *   EVALUATION_INCOMPLETE the engine was asked and its answer could not be
 *                         read, which is not the same as no decision
 *   POLICY_INFERRED       a text scan of policy source matched; no engine
 *                         evaluated anything, so this is not a decision at all
 *
 * Neither absence state is styled as success or failure. Absence of a
 * decision is a real, honest state; coloring it green would claim a
 * permission nobody granted, and coloring an inference like a decision would
 * be worse: it would launder a substring match into governance evidence.
 */
import type React from 'react'
import {
  Check,
  CircleHelp,
  FileSearch,
  MinusCircle,
  ShieldAlert,
  ShieldOff,
} from 'lucide-react'
import type { PolicyDecision } from './governedTypes'

export interface PolicyDecisionBadgeProps {
  decision: PolicyDecision
  /** `sm` for inline chips, `md` for card headers. */
  size?: 'sm' | 'md'
  /** Reason text shown as a tooltip; also appended to the accessible name. */
  reason?: string | null
  className?: string
}

interface DecisionPresentation {
  /** Visible text. Never omitted — this is what makes the badge readable. */
  label: string
  /** Distinct glyph per decision, not a recolored copy of the same mark. */
  Icon: typeof Check
  /** Accessible name. Differs per decision by contract, asserted in tests. */
  accessibleName: string
  fg: string
  bg: string
  border: string
}

const PRESENTATION: Record<PolicyDecision, DecisionPresentation> = {
  ALLOW: {
    label: 'ALLOW',
    Icon: Check,
    accessibleName:
      'Policy decision: ALLOW — the policy permitted the action; execution is reported separately',
    fg: 'var(--gov-allow-fg)',
    bg: 'var(--gov-allow-bg)',
    border: 'var(--gov-allow-border)',
  },
  DENY: {
    label: 'DENY',
    Icon: ShieldOff,
    accessibleName:
      'Policy decision: DENY — blocked before execution, the tool did not run',
    fg: 'var(--gov-deny-fg)',
    bg: 'var(--gov-deny-bg)',
    border: 'var(--gov-deny-border)',
  },
  WOULD_DENY: {
    label: 'WOULD DENY',
    Icon: ShieldAlert,
    accessibleName:
      'Policy decision: WOULD DENY — a deny event was recorded under LOG_ONLY, so it was observed but not enforced and the tool ran',
    fg: 'var(--gov-rail-fallback-fg)',
    bg: 'var(--gov-rail-fallback-bg)',
    border: 'var(--gov-degraded-border)',
  },
  NOT_EVALUATED: {
    label: 'NOT EVALUATED',
    Icon: MinusCircle,
    accessibleName: 'Policy decision: not evaluated for this turn',
    fg: 'var(--gov-neutral-fg)',
    bg: 'var(--gov-neutral-bg)',
    border: 'var(--gov-neutral-border)',
  },
  EVALUATION_INCOMPLETE: {
    label: 'EVALUATION INCOMPLETE',
    Icon: CircleHelp,
    accessibleName:
      'Policy decision: evaluation incomplete — the engine was asked and its decision could not be read',
    fg: 'var(--gov-unavailable-fg)',
    bg: 'var(--gov-unavailable-bg)',
    border: 'var(--gov-unavailable-border)',
  },
  POLICY_INFERRED: {
    label: 'POLICY INFERRED',
    Icon: FileSearch,
    accessibleName:
      'Inferred from policy text, not a decision — no engine evaluated this action',
    fg: 'var(--gov-unavailable-fg)',
    bg: 'var(--gov-unavailable-bg)',
    border: 'var(--gov-unavailable-border)',
  },
}

export const PolicyDecisionBadge: React.FC<PolicyDecisionBadgeProps> = ({
  decision,
  size = 'sm',
  reason,
  className,
}) => {
  const p = PRESENTATION[decision] ?? PRESENTATION.NOT_EVALUATED
  const iconSize = size === 'md' ? 15 : 13
  const accessibleName = reason
    ? `${p.accessibleName}. Reason: ${reason}`
    : p.accessibleName

  return (
    <span
      className={className}
      data-testid="policy-decision-badge"
      data-decision={decision}
      title={reason ?? p.accessibleName}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        fontFamily: 'var(--dl-font-mono)',
        fontSize: size === 'md' ? '13px' : '12px',
        letterSpacing: '0.1em',
        fontWeight: 600,
        color: p.fg,
        backgroundColor: p.bg,
        border: `1px solid ${p.border}`,
        borderRadius: 'var(--gov-radius-sm)',
        padding: size === 'md' ? '4px 9px' : '2px 7px',
        whiteSpace: 'nowrap',
      }}
    >
      <p.Icon size={iconSize} aria-hidden="true" />
      {/* Visible text carries the decision for sighted users; the hidden
          span carries the full claim for assistive technology. */}
      <span aria-hidden="true">{p.label}</span>
      <span className="gov-visually-hidden">{accessibleName}</span>
    </span>
  )
}

export default PolicyDecisionBadge
