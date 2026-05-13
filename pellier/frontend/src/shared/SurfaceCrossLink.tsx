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
 * Visual: italic Fraunces verb + a thin terracotta arrow, kept small
 * enough to live inline next to a section eyebrow. The same
 * vocabulary (`see · this · in · the · Boutique`) on every Atelier
 * surface keeps the round trip predictable.
 */
import React from 'react'

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
}

const ACCENT = '#a8423a'
const FRAUNCES_STACK = "'Fraunces', Georgia, serif"

export const SurfaceCrossLink: React.FC<SurfaceCrossLinkProps> = ({
  direction,
  href,
  label,
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
    <a
      href={targetHref}
      data-testid={`surface-cross-link-${direction}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontFamily: FRAUNCES_STACK,
        fontStyle: 'italic',
        fontSize: 14,
        color: ACCENT,
        textDecoration: 'none',
        borderBottom: '1px dotted rgba(168,66,58,0.35)',
        paddingBottom: 1,
        transition: 'border-color 0.15s, color 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderBottomColor = 'rgba(168,66,58,0.85)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderBottomColor = 'rgba(168,66,58,0.35)'
      }}
    >
      <span>{label ?? defaultLabel}</span>
      <span aria-hidden="true">{arrow}</span>
    </a>
  )
}
