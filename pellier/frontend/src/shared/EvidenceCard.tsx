/**
 * EvidenceCard — the container an evidence panel sits in.
 *
 * The two technical surfaces were carrying six card radii between them: 16px
 * for the Observatory working card, 12px for the proof tabs and the desk, 10px
 * for the cheat sheet, 8px for the Proof Board's inline panels, 14px for the
 * section frame. Nothing distinguished them semantically; they were written on
 * different days. One radius, 14px, and the differences that remain say
 * something.
 *
 * Two of them:
 *
 *   `quiet` sits on recessed paper with no shadow. It is for a panel that has
 *   nothing to report yet: an unrecorded measurement, an empty ledger. A card
 *   that is empty should not be lifted off the page as though it had content.
 *
 *   `tone` marks a card whose subject has a system state, using a 28px tick
 *   crossing the top edge rather than a coloured bar down one side. A bar
 *   turns every card into an alert; the tick is the mark the Pellier section
 *   frame has used since the beginning.
 *
 * One resting shadow, warm (`--gov-shadow-card`), and no hover lift. Lift is
 * an affordance and these cards are not pressable; `ExpCard` keeps its lift
 * because it takes an `onClick`.
 */
import type React from 'react'

import './primitives.css'

export type EvidenceCardTone =
  | 'neutral'
  | 'brand'
  | 'ok'
  | 'attention'
  | 'degraded'

export type EvidenceCardElement = 'div' | 'section' | 'article' | 'aside' | 'li'

export interface EvidenceCardProps {
  children: React.ReactNode
  /** Recessed paper, no shadow. For a panel with nothing to report. */
  quiet?: boolean
  /** Draws a 28px tick in the tone colour across the card's top edge. */
  tone?: EvidenceCardTone
  /** 24px by default, 20px for a card in a dense row. */
  padding?: 'default' | 'compact'
  as?: EvidenceCardElement
  id?: string
  className?: string
  style?: React.CSSProperties
  'aria-label'?: string
  'aria-labelledby'?: string
  'data-testid'?: string
}

const TONE_COLOR: Record<EvidenceCardTone, string> = {
  neutral: 'transparent',
  brand: 'var(--pellier-accent)',
  ok: 'var(--obs-status-ok-fg, var(--dl-ok))',
  attention: 'var(--obs-status-attention-fg, var(--dl-accent))',
  degraded: 'var(--obs-status-degraded-fg, var(--dl-warn))',
}

export const EvidenceCard: React.FC<EvidenceCardProps> = ({
  children,
  quiet = false,
  tone = 'neutral',
  padding = 'default',
  as: Tag = 'div',
  id,
  className,
  style,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledBy,
  'data-testid': testId,
}) => (
  <Tag
    id={id}
    className={`gov-evidence-card${className ? ` ${className}` : ''}`}
    data-tone={tone}
    data-quiet={quiet ? 'true' : undefined}
    data-padding={padding}
    data-testid={testId}
    aria-label={ariaLabel}
    aria-labelledby={ariaLabelledBy}
    style={{
      position: 'relative',
      padding: padding === 'compact' ? '20px' : '24px',
      border: '1px solid var(--obs-rule-1)',
      borderRadius: 'var(--gov-radius-lg)',
      background: quiet ? 'var(--obs-panel-muted)' : 'var(--obs-panel)',
      boxShadow: quiet ? 'none' : 'var(--gov-shadow-card)',
      ['--gov-card-tone' as string]: TONE_COLOR[tone] ?? TONE_COLOR.neutral,
      ...style,
    }}
  >
    {children}
  </Tag>
)

export default EvidenceCard
