/**
 * ProductCard: one card in the collection, direction A.
 *
 * A photograph in a rounded frame with a hairline inner border, then the
 * brand or maker, the name and price on one row, and one plain stock line
 * as a status tag: "In stock", "In stock in Austin and Portland", "Sold
 * out". The photograph and the name both lead to the piece's page. A piece
 * the answer recommended carries a small "Pellier's pick" tag on its photo.
 *
 * Scroll reveal, gated by two stacked safety defenses:
 *
 *   1. Visible pre-reveal: opacity stays at 1, so a stalled observer never
 *      hides product content; the reveal motion comes from transform only.
 *   2. Safety timeout: 500ms after mount, a card at or near the viewport is
 *      force-revealed regardless of observer state.
 *
 * `prefers-reduced-motion: reduce` skips the observer entirely and paints
 * the card at its final state on first render.
 *
 * The card renders react-router `Link`s to `/product/:id`, so it must be
 * mounted inside a router. Tests wrap it in `MemoryRouter`.
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { RESULTS } from '../copy'
import type { PellierProduct } from '../services/types'
import { stockLine } from '../utils/stockLine'
import ResponsiveImage from './ResponsiveImage'
import StatusTag from './turn/StatusTag'
import '../styles/turn.css'

interface ProductCardProps {
  product: PellierProduct
  /** Row-wise index (0..2). Drives a compact per-column stagger. */
  index: number
  /** One of the pieces the answer recommended, in the results grid. */
  pick?: boolean
}

// Per-column stagger in ms. Columns within a row play at 0ms, 50ms, 100ms so
// the catalog settles quickly while retaining a subtle left-to-right sweep.
const STAGGER_MS = 50

// Columns per row in the desktop grid. The stagger math uses the widest case
// so the sweep is consistent on desktop.
const GRID_COLUMNS = 3

// If the observer has not revealed the card within this window after mount,
// force the final state for a card that is on screen.
const SAFETY_TIMEOUT_MS = 500

// Keep this at 1 so a stalled observer never hides product content.
const PRE_REVEAL_OPACITY = 1

const REVEAL_EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function ProductCard({ product, index, pick = false }: ProductCardProps) {
  // Router `basename` prefixes this for the Workshop Studio /ports/8000/
  // proxy, so the path stays base-relative here.
  const detailPath = `/product/${product.id}`
  const stock = stockLine(product)
  const [isVisible, setIsVisible] = useState<boolean>(() => prefersReducedMotion())
  const cardRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const node = cardRef.current
    if (!node) return

    if (prefersReducedMotion()) {
      setIsVisible(true)
      return
    }

    const safetyTimeout = window.setTimeout(() => {
      const rect = node.getBoundingClientRect()
      const viewportH = window.innerHeight || document.documentElement.clientHeight
      const isAtOrNearViewport = rect.top < viewportH && rect.bottom > 0
      if (isAtOrNearViewport) {
        setIsVisible(true)
      }
    }, SAFETY_TIMEOUT_MS)

    if (typeof window.IntersectionObserver === 'undefined') {
      window.clearTimeout(safetyTimeout)
      setIsVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const delay = (Math.max(0, index) % GRID_COLUMNS) * STAGGER_MS
          window.setTimeout(() => setIsVisible(true), delay)
          observer.unobserve(entry.target)
          window.clearTimeout(safetyTimeout)
        }
      },
      { threshold: 0.05, rootMargin: '0px 0px -5% 0px' },
    )
    observer.observe(node)

    return () => {
      window.clearTimeout(safetyTimeout)
      observer.disconnect()
    }
  }, [index])

  return (
    <article
      ref={cardRef}
      data-testid={`product-card-${product.id}`}
      data-index={index}
      data-revealed={isVisible}
      data-pick={pick ? 'true' : undefined}
      className="pellier-card"
      style={{
        opacity: isVisible ? 1 : PRE_REVEAL_OPACITY,
        transform: isVisible ? 'translateY(0) scale(1)' : 'translateY(12px) scale(0.99)',
        transition: `opacity 220ms ${REVEAL_EASE}, transform 260ms ${REVEAL_EASE}`,
      } as CSSProperties}
    >
      {/* The photograph is a decorative duplicate of the name's link: out of
          the accessibility tree and the tab order, so assistive tech and
          keyboard users get exactly one link per card. */}
      <Link to={detailPath} aria-hidden="true" tabIndex={-1} className="pellier-card-photo">
        <ResponsiveImage
          src={product.imageUrl}
          alt={product.name}
          widths={[480, 960, 1122]}
          sizes="(min-width: 700px) 360px, 50vw"
          loading="lazy"
          decoding="async"
          pictureClassName="block h-full w-full"
          className="h-full w-full object-cover"
          style={{ objectPosition: product.imagePosition ?? 'center center' }}
        />
      </Link>
      {/* Over the photo, but outside its hidden link, so it is read. */}
      {pick ? <span className="pellier-card-pick">{RESULTS.PICK}</span> : null}

      <div className="pellier-card-copy">
        <span className="pellier-card-brand">{product.brand}</span>
        <div className="pellier-card-row">
          <h3 className="pellier-card-name">
            <Link to={detailPath} data-testid={`product-card-link-${product.id}`}>
              {product.name}
            </Link>
          </h3>
          <span className="pellier-card-price">${product.price}</span>
        </div>
        <StatusTag tone={stock.tone}>{stock.label}</StatusTag>
      </div>
    </article>
  )
}
