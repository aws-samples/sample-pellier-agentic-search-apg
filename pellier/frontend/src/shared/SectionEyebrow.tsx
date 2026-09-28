/**
 * SectionEyebrow — the one label that opens a section.
 *
 * Both technical surfaces had drifted to five eyebrow recipes. The
 * Observatory shipped a sans version with a dot, a legacy `.at-section-eyebrow`
 * class, and three mono recipes; the Operator desk carried six more selectors,
 * one of them mono at 10px. Five registers for one job is what makes a surface
 * read as several products.
 *
 * One recipe: Instrument Sans, 13px, 600, sentence case. It was 11px tracked
 * uppercase, and with an eyebrow over most sections that made the technical
 * surfaces read louder than the storefront while saying less; a label in the
 * reading face at caption size carries the same structure quietly.
 *
 * Sans, not mono, and this is the load-bearing decision. Monospace on these
 * surfaces means "this is an identifier, a table, a duration, a value you
 * could paste into psql". A section label is none of those. Spending mono on
 * prose labels is what left the real identifiers with no way to stand out.
 *
 * `tone="brand"` names a section that belongs to the product's own structure:
 * ink text with the burgundy mark on the dot, so the authority colour stays a
 * point rather than a line of text on every section. `tone="muted"` names a
 * subordinate label inside a card.
 */
import type React from 'react'

export type SectionEyebrowTone = 'brand' | 'muted'

export interface SectionEyebrowProps {
  children: React.ReactNode
  /** `brand` for a section opener, `muted` for a label inside a card. */
  tone?: SectionEyebrowTone
  /** The leading dot. Drop it where the eyebrow is already inside a rule. */
  dot?: boolean
  as?: 'span' | 'div' | 'p'
  id?: string
  className?: string
  'data-testid'?: string
}

const TONE_COLOR: Record<SectionEyebrowTone, string> = {
  brand: 'var(--obs-ink-2)',
  muted: 'var(--obs-ink-4)',
}

const DOT_COLOR: Record<SectionEyebrowTone, string> = {
  brand: 'var(--pellier-burgundy)',
  muted: 'currentColor',
}

export const SectionEyebrow: React.FC<SectionEyebrowProps> = ({
  children,
  tone = 'brand',
  dot = true,
  as: Tag = 'span',
  id,
  className,
  'data-testid': testId,
}) => {
  const color = TONE_COLOR[tone] ?? TONE_COLOR.brand

  return (
    <Tag
      id={id}
      className={className}
      data-tone={tone}
      data-testid={testId}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontFamily: 'var(--obs-heading)',
        fontSize: '13px',
        fontWeight: 600,
        letterSpacing: 0,
        lineHeight: 1.2,
        color,
      }}
    >
      {dot ? (
        <span
          aria-hidden="true"
          style={{
            width: '5px',
            height: '5px',
            borderRadius: '999px',
            background: DOT_COLOR[tone] ?? DOT_COLOR.brand,
            flexShrink: 0,
          }}
        />
      ) : null}
      {children}
    </Tag>
  )
}

export default SectionEyebrow
