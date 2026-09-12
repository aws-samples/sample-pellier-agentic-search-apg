/**
 * SurfaceCrossLink — pill link that connects the shopper and evidence surfaces.
 *
 * Two preset modes:
 *   - "to-pellier" - used on Observatory surfaces. Reads "See this in
 *      Pellier" and links back to the storefront, optionally
 *      with an `?ask=` query that opens the chat drawer with a
 *      pre-filled prompt that exercises this concept.
 *   - "to-observatory" — used on Pellier surfaces. Reads "How this works
 *      " and deep-links to the Observatory route that explains the
 *      concept (memory, tools, agents, etc).
 *
 * Uses the existing rounded Pellier control and sans typography.
 * Consistent vocabulary (`See this in Pellier`) on every Observatory
 * surface keeps the round trip predictable.
 */
import React from 'react'
import { Link } from 'react-router-dom'

export type CrossLinkDirection = 'to-pellier' | 'to-observatory'

export interface SurfaceCrossLinkProps {
  direction: CrossLinkDirection
  /**
   * For `to-pellier`: optional `?ask=` query that auto-fires the
   * Pellier chat drawer with this prompt. For `to-observatory`: the
   * Observatory path to navigate to (e.g. "/observatory/memory").
   */
  href?: string
  /** Override the default copy. */
  label?: string
  /** Use upright text when the link sits inside sans/body UI copy. */
  italic?: boolean
}

export const SurfaceCrossLink: React.FC<SurfaceCrossLinkProps> = ({ direction, href, label }) => (
  <Link
    to={href ?? (direction === 'to-pellier' ? '/' : '/observatory')}
    data-testid={`surface-cross-link-${direction}`}
    className="pellier-action-quiet"
  >
    {label ?? (direction === 'to-pellier' ? 'See this in Pellier' : 'How this works')}
  </Link>
)
