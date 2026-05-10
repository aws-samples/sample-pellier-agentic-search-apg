/**
 * SectionFrame — the cream-1 box with hairline border + burgundy top-left
 * tick. Used as the conceptual hero on most pages ("The network",
 * "The flow", "The schema", etc.).
 *
 * Passes children through so callers can lay out their own body inside
 * the frame — two-column grids, svg diagrams, tables, whatever.
 */
import type { ReactNode } from 'react'
import SectionEyebrow from './SectionEyebrow'

export interface SectionFrameProps {
  /** Small-caps burgundy eyebrow above the title. */
  eyebrow?: string
  /** Section title — may include ``<em>`` markup. */
  title?: ReactNode
  /** Italic serif description. */
  description?: ReactNode
  /** Body content. */
  children: ReactNode
  /** Variant — ``elevated`` swaps cream-1 background for cream-elev (rare). */
  variant?: 'default' | 'elevated'
}

export default function SectionFrame({
  eyebrow,
  title,
  description,
  children,
  variant = 'default',
}: SectionFrameProps) {
  const className = variant === 'elevated' ? 'at-frame at-frame-elevated' : 'at-frame'
  return (
    <section className={className}>
      {eyebrow && <SectionEyebrow>{eyebrow}</SectionEyebrow>}
      {title && <h2 className="at-section-title">{title}</h2>}
      {description && <p className="at-section-desc">{description}</p>}
      {children}
    </section>
  )
}
