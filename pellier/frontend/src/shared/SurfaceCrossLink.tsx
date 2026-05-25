/**
 * SurfaceCrossLink — small inline anchor that bridges the two surfaces.
 *
 * Two preset modes:
 *   - "to-boutique" — used on Atelier surfaces. Reads "→ See this in
 *      the Boutique" and links back to the storefront, optionally
 *      with an `?ask=` query that opens the chat drawer with a
 *      pre-filled prompt that exercises this concept.
 *   - "to-atelier" — used on Boutique surfaces. Reads "How this works
 *      →" and deep-links to the Atelier route that explains the
 *      concept (memory, tools, agents, etc).
 *
 * Visual: Instrument Serif / Fraunces italic, 15px, terracotta accent,
 * subtle dotted underline — reads as editorial caption, not a banner CTA.
 * vocabulary (`see · this · in · the · Boutique`) on every Atelier
 * surface keeps the round trip predictable.
 */
import React from 'react'
import { Link } from 'react-router-dom'

export type CrossLinkDirection = 'to-boutique' | 'to-atelier'

export interface SurfaceCrossLinkProps {
  direction: CrossLinkDirection
  /**
   * For `to-boutique`: optional `?ask=` query that auto-fires the
   * Boutique chat drawer with this prompt. For `to-atelier`: the
   * Atelier path to navigate to (e.g. "/atelier/memory").
   */
  href?: string
  /** Override the default copy. */
  label?: string
  /** Use upright text when the link sits inside sans/body UI copy. */
  italic?: boolean
}

const ACCENT = 'var(--accent)'

export const SurfaceCrossLink: React.FC<SurfaceCrossLinkProps> = ({
  direction,
  href,
  label,
  italic = true,
}) => {
  const defaultLabel =
    direction === 'to-boutique'
      ? 'See this in the Boutique'
      : 'How this works'

  const targetHref =
    href ??
    (direction === 'to-boutique' ? '/' : '/atelier')

  const arrow = direction === 'to-boutique' ? '→' : '→'

  return (
    <Link
      to={targetHref}
      data-testid={`surface-cross-link-${direction}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontFamily: 'var(--serif)',
        fontStyle: italic ? 'italic' : 'normal',
        fontSize: 15,
        fontWeight: 400,
        letterSpacing: '-0.01em',
        color: ACCENT,
        textDecoration: 'none',
        borderBottom: '1px dotted color-mix(in srgb, var(--accent) 42%, transparent)',
        paddingBottom: 2,
        transition: 'border-color 0.15s, color 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderBottomColor =
          'color-mix(in srgb, var(--accent) 78%, transparent)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderBottomColor =
          'color-mix(in srgb, var(--accent) 42%, transparent)'
      }}
    >
      <span>{label ?? defaultLabel}</span>
      <span aria-hidden="true">{arrow}</span>
    </Link>
  )
}
