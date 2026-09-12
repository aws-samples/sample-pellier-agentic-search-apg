/**
 * Return-to-storefront link, shown on the working surfaces.
 *
 * The Operator desk and the Observatory both need an unmistakable way back to
 * Pellier. A text link reads as one more nav item; the mark reads as home, so
 * both surfaces use the shared outlined mark and lowercase wordmark.
 *
 * Sized a step down from the storefront's own wordmark: this is navigation
 * back, not the current surface's identity, and it must not compete with the
 * surface wordmark on the opposite side of the bar.
 */

import React from 'react'
import { Link } from 'react-router-dom'
import { NAV } from '../copy'
import PellierMark from './PellierMark'

interface PellierHomeLinkProps {
  /** Preserved per surface so existing tests keep their handle. */
  testId?: string
  className?: string
  /** Name the destination when Pellier is not the current surface. */
  label?: string
  ariaLabel?: string
}

const PellierHomeLink: React.FC<PellierHomeLinkProps> = ({
  testId = 'pellier-home-link',
  className,
  label = NAV.WORDMARK,
  ariaLabel = `Back to ${NAV.WORDMARK}`,
}) => (
  <Link
    to="/"
    data-testid={testId}
    aria-label={ariaLabel}
    title={ariaLabel}
    className={['pellier-home-link', className].filter(Boolean).join(' ')}
  >
    <PellierMark size={26} />
    <span aria-hidden="true" className="pellier-home-wordmark">
      {label === NAV.WORDMARK ? <>pellier<span className="pellier-home-wordmark-dot">.</span></> : label}
    </span>
  </Link>
)

export default PellierHomeLink
