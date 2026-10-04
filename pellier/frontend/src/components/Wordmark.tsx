/**
 * The pellier. wordmark, signature element 1: lowercase `pellier` in
 * Fraunces 400 at -1.8px tracking, plus the copper period. 31px in the
 * header, 36px in the footer. Ink with a copper dot in light, ivory with the
 * dark theme's copper on black; both come from `--pellier-copper`.
 *
 * The header shows the wordmark alone. The square p. mark is the favicon and
 * Ask Pellier's avatar (see PellierMark), never the header.
 */
import { Link } from 'react-router-dom'
import '../styles/surface-navigation.css'

interface WordmarkProps {
  /** Header at 31px, footer at 36px. */
  size?: 'header' | 'footer'
  ariaLabel?: string
  className?: string
}

export default function Wordmark({ size = 'header', ariaLabel = 'Pellier home', className }: WordmarkProps) {
  return (
    <Link
      to="/"
      className={['pellier-brand', size === 'footer' ? 'pellier-brand-footer' : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
      aria-label={ariaLabel}
      data-testid="pellier-wordmark"
    >
      <span aria-hidden="true">pellier</span>
      <span className="pellier-brand-dot" aria-hidden="true">.</span>
    </Link>
  )
}
