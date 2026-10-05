/**
 * The pellier. wordmark, signature element 1: lowercase `pellier` in
 * Fraunces 400 at -1.8px tracking, plus the copper period. 31px in the
 * header, 36px in the footer. Ink with a copper dot in light, ivory with the
 * dark theme's copper on black; both come from `--pellier-copper`.
 *
 * This file is the only place that sets Fraunces. Every heading and title
 * is Instrument Sans; `token_guard.test.ts` fails on a Fraunces, display or
 * serif reference anywhere else in src/. The wordmark's letters and the
 * square p. mark below both take their face from `BRAND_FACE`.
 *
 * The header shows the wordmark alone. The square p. mark is the favicon and
 * Ask Pellier's avatar, never the header.
 *
 * The wordmark always returns to the default home: the whole store, an empty
 * home bar and the top of the page, even on `/` with results showing. The
 * Ask Pellier conversation and the signed-in shopper stay as they are.
 */
import { Link, useLocation } from 'react-router-dom'
import '@fontsource-variable/fraunces'
import { useStoreResults } from '../contexts/StoreResultsContext'
import '../styles/surface-navigation.css'

const BRAND_FACE = { fontFamily: 'var(--dl-font-display)' } as const

/**
 * The wordmark's letters alone, for a lockup that is not the home link: the
 * sign-in page's own link and photograph, and the sign-in dialog. The size
 * and tracking come from the caller's class (`.pellier-brand`).
 */
export function WordmarkLetters() {
  return (
    <>
      <span aria-hidden="true" style={BRAND_FACE}>pellier</span>
      <span className="pellier-brand-dot" aria-hidden="true" style={BRAND_FACE}>.</span>
    </>
  )
}

interface WordmarkProps {
  /** Header at 31px, footer at 36px. */
  size?: 'header' | 'footer'
  ariaLabel?: string
  className?: string
}

export default function Wordmark({ size = 'header', ariaLabel = 'Pellier home', className }: WordmarkProps) {
  const results = useStoreResults()
  const { pathname } = useLocation()
  const goHome = () => {
    results?.clear()
    // Another route scrolls to the top when it changes; on `/` nothing changes.
    if (pathname !== '/') return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduce ? 'instant' : 'smooth' })
  }
  return (
    <Link
      to="/"
      onClick={goHome}
      className={['pellier-brand', size === 'footer' ? 'pellier-brand-footer' : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
      aria-label={ariaLabel}
      data-testid="pellier-wordmark"
    >
      <WordmarkLetters />
    </Link>
  )
}

/**
 * The square p. mark: Ask Pellier's avatar, drawn from tokens so it follows
 * the theme (an ink square with an on-ink p in light, ivory with a black p in
 * dark; the dot is always copper). `public/favicon.svg`, `favicon.ico` and
 * `apple-touch-icon.png` draw the light mark: an ivory p. on the ink tile.
 *
 * The p and its dot share one span, the tile's single grid item, so the dot
 * sits beside the p rather than in a second grid row below the tile.
 */
export function PellierMark({
  size = 20,
  className,
  'data-testid': testId,
}: {
  size?: number
  className?: string
  'data-testid'?: string
}) {
  return (
    <span
      className={['pellier-mark', className ?? ''].filter(Boolean).join(' ')}
      aria-hidden="true"
      data-testid={testId}
      style={{ ...BRAND_FACE, width: size, height: size, fontSize: Math.round(size * 0.68) }}
    >
      <span>p<span className="pellier-brand-dot">.</span></span>
    </span>
  )
}
