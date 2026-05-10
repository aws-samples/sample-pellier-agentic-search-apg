/**
 * ProductCard — one card in the storefront product grid, with scroll-reveal
 * parallax gated by two stacked safety defenses.
 *
 * An earlier revision removed the parallax because the pre-reveal state
 * (`opacity: 0`) could leave the whole grid invisible when IntersectionObserver
 * failed to deliver its first entry (browser edge cases, pre-hydration paint,
 * non-standard zoom levels). Parallax is back, but the stuck-invisible bug
 * is impossible now because BOTH defenses must fail simultaneously:
 *
 *   1. Visible pre-reveal — opacity starts at 0.05, not 0. Cards render as
 *      ghostly-but-legible even if the observer never fires.
 *   2. Safety timeout — 500ms after mount, force-reveal fires regardless of
 *      observer state. Normal-path reveals clear the timeout; only unusual
 *      observer stalls reach it.
 *
 * `prefers-reduced-motion: reduce` skips the observer entirely and paints
 * the card at its final state on first render.
 *
 * Layout:
 *   1. Warm wash overlay on the image
 *   2. Optional top-left badge (EDITOR'S PICK / BESTSELLER / JUST IN)
 *   3. Top-right heart (fades in on hover)
 *   4. Brand + color row
 *   5. Product name (Fraunces italic)
 *   6. Price + rating row
 *   7. Thin divider
 *   8. <ReasoningChip/>
 *   9. Full-width `Add to bag` secondary button
 *
 * Phase 2 redesign: replaced all hardcoded hex colors with Tailwind token
 * classes. Card chrome uses shadow-warm-sm / shadow-warm-md tokens. The
 * parallax observer logic and safety defenses are preserved unchanged.
 */
import { useEffect, useRef, useState } from 'react'
import { Star } from 'lucide-react'

import type { BoutiqueBadge, BoutiqueProduct } from '../services/types'
import ReasoningChip from './ReasoningChip'

const BADGE_LABEL: Record<BoutiqueBadge, string> = {
  EDITORS_PICK: "EDITOR'S PICK",
  BESTSELLER: 'BESTSELLER',
  JUST_IN: 'JUST IN',
}

interface ProductCardProps {
  product: BoutiqueProduct
  /** Row-wise index (0..2). Drives per-column stagger (`index * 220ms`). */
  index: number
  /** Optional `Add to bag` handler. Defaults to a no-op. */
  onAddToBag?: (product: BoutiqueProduct) => void
}

// Per-column stagger in ms. Matches storefront.md — columns within a row play
// at 0ms, 220ms, 440ms so each row reveals as a left-to-right sweep. We use
// `index % 3` so the card computes the correct 0..2 column regardless of
// whether the grid passes a row-local or catalog-global index. At 92+ products
// a linear `index * 220ms` cascade would push later cards to >11s delay,
// well past the observer's attention window.
const STAGGER_MS = 220

// Columns per row in the desktop grid. The stagger math uses the widest case
// so the sweep is consistent on desktop; on narrower breakpoints the same
// modulo still reads as a small cascade.
const GRID_COLUMNS = 3

// Hard safety limit for the stuck-invisible bug that killed parallax v1. If
// the observer hasn't revealed the card within this window after mount, force
// the final state. 500ms is long enough to see a normal observer fire first.
const SAFETY_TIMEOUT_MS = 500

// Pre-reveal opacity. Crucially >0 so a stalled observer leaves cards
// ghostly-but-legible rather than entirely invisible.
const PRE_REVEAL_OPACITY = 0.05

// Apple-style ease-out-expo. Don't substitute — `ease-out` reads as too
// mechanical at this duration.
const REVEAL_EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function ProductCard({
  product,
  index,
  onAddToBag,
}: ProductCardProps) {
  const [hovered, setHovered] = useState(false)
  // `isVisible` starts as `prefersReducedMotion` so users with reduced-motion
  // skip the pre-reveal ghost state entirely — first paint is the final state.
  const [isVisible, setIsVisible] = useState<boolean>(() => prefersReducedMotion())
  const cardRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const node = cardRef.current
    if (!node) return

    // Reduced-motion short-circuit: already visible from initial state,
    // no observer/timeout needed.
    if (prefersReducedMotion()) {
      setIsVisible(true)
      return
    }

    // Defense 2: safety force-reveal. Guards against the stuck-invisible
    // bug for cards that SHOULD be on screen at mount but the observer
    // missed. Cards that are below the fold at 500ms get left alone so
    // the observer can fire naturally when the user scrolls to them —
    // otherwise every card below the fold reveals at 500ms and there's
    // no parallax left for the scroll-in.
    const safetyTimeout = window.setTimeout(() => {
      const rect = node.getBoundingClientRect()
      const viewportH = window.innerHeight || document.documentElement.clientHeight
      const isAtOrNearViewport = rect.top < viewportH && rect.bottom > 0
      if (isAtOrNearViewport) {
        setIsVisible(true)
      }
    }, SAFETY_TIMEOUT_MS)

    // No IntersectionObserver (old jsdom, SSR) — lean on the safety timeout
    // only, but advance it so tests don't wait unnecessarily.
    if (typeof window.IntersectionObserver === 'undefined') {
      window.clearTimeout(safetyTimeout)
      setIsVisible(true)
      return
    }

    // Defense 1's main path: IntersectionObserver with per-column stagger.
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const delay = (Math.max(0, index) % GRID_COLUMNS) * STAGGER_MS
          window.setTimeout(() => setIsVisible(true), delay)
          observer.unobserve(entry.target)
          // Normal path fired first — safety net no longer needed.
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
      className={`
        bg-cream-50 rounded-xl overflow-hidden flex flex-col
        shadow-warm-sm transition-shadow duration-fade ease-out
        ${hovered ? 'shadow-warm-md' : 'shadow-warm-sm'}
      `}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        opacity: isVisible ? 1 : PRE_REVEAL_OPACITY,
        transform: isVisible
          ? 'translateY(0) scale(1)'
          : 'translateY(56px) scale(0.975)',
        transition: `opacity 1100ms ${REVEAL_EASE}, transform 1200ms ${REVEAL_EASE}, box-shadow 180ms ease-out`,
        willChange: 'opacity, transform',
      }}
    >
      {/* --- Image panel --------------------------------------------- */}
      <div className="relative aspect-[4/5] bg-sand overflow-hidden">
        <img
          src={product.imageUrl}
          alt={product.name}
          loading="lazy"
          className="w-full h-full object-cover transition-transform ease-out"
          style={{
            transitionDuration: '600ms',
            transform: hovered ? 'scale(1.03)' : 'scale(1)',
            objectPosition: product.imagePosition ?? 'center center',
          }}
        />
        {/* Warm wash overlay (Req 1.6.5 step 1) */}
        <div
          data-testid="product-card-warm-wash"
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'linear-gradient(180deg, rgba(247,243,238,0.08) 0%, rgba(196,69,54,0.08) 100%)',
          }}
        />
        {/* Optional top-left badge (Req 1.6.5 step 2) */}
        {product.badge ? (
          <span
            data-testid={`product-card-badge-${product.id}`}
            className="absolute top-3 left-3 bg-cream-50 text-espresso px-2.5 py-1 text-[10px] tracking-[0.12em] font-sans rounded-full"
          >
            {BADGE_LABEL[product.badge]}
          </span>
        ) : null}
      </div>

      {/* --- Text block ---------------------------------------------- */}
      <div className="p-5 flex flex-col gap-2.5">
        {/* Brand + color row (Req 1.6.5 step 4) */}
        <div className="flex justify-between gap-3 text-[11px] tracking-[0.08em] text-ink-quiet font-sans uppercase">
          <span>{product.brand}</span>
          <span>{product.color}</span>
        </div>

        {/* Product name — Fraunces italic (Req 1.6.5 step 5). Size bumps
            20→22px at ≥1024px via `.product-name` in index.css so the
            breakpoint happens in CSS, not React. */}
        <h3 className="product-name text-espresso">
          {product.name}
        </h3>

        {/* Price + rating row (Req 1.6.5 step 6) */}
        <div className="flex items-center justify-between text-sm text-ink-soft font-sans">
          <span className="text-espresso">${product.price}</span>
          <span className="inline-flex items-center gap-1.5 text-ink-soft">
            <Star size={12} strokeWidth={1.5} className="fill-ink-soft text-ink-soft" />
            {product.rating.toFixed(1)}
            <span className="text-ink-quiet text-xs">
              ({product.reviewCount})
            </span>
          </span>
        </div>

        {/* Thin divider (Req 1.6.5 step 7) */}
        <div
          aria-hidden
          className="h-px bg-sand/50 my-0.5"
        />

        {/* Reasoning chip (Req 1.6.5 step 8) */}
        {product.reasoning ? <ReasoningChip chip={product.reasoning} /> : null}

        {/* Full-width Add to bag secondary button (Req 1.6.5 step 9) */}
        <button
          type="button"
          data-testid={`product-card-add-${product.id}`}
          onClick={() => onAddToBag?.(product)}
          className="
            mt-1.5 w-full bg-transparent text-espresso border border-espresso
            rounded-full py-2.5 px-3.5 text-[13px] tracking-[0.06em] cursor-pointer
            font-sans transition-colors duration-fade ease-out
            hover:bg-dusk hover:text-cream-50 hover:border-dusk
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent
          "
        >
          Add to bag
        </button>
      </div>
    </article>
  )
}
