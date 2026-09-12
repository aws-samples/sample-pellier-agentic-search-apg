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
 *   1. Visible pre-reveal — opacity stays at 1. Cards remain legible even if
 *      the observer never fires; the reveal motion comes from transform only.
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
 *   5. Product name (Fraunces italic), linking to the piece's page
 *   6. Price + rating row
 *   7. Thin divider
 *   8. <ReasoningChip/>
 *   9. Full-width `Add to bag` secondary button
 *
 * The card renders react-router `Link`s to `/product/:id`, so it must be
 * mounted inside a router. Tests wrap it in `MemoryRouter`.
 *
 * Phase 2 redesign: replaced all hardcoded hex colors with Tailwind token
 * classes. Card chrome uses shadow-warm-sm / shadow-warm-md tokens. The
 * parallax observer logic and safety defenses are preserved unchanged.
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, Star } from 'lucide-react'

import type { PellierBadge, PellierProduct } from '../services/types'
import ReasoningChip from './ReasoningChip'
import ResponsiveImage from './ResponsiveImage'
import { TraceChip } from '../shared'

const BADGE_LABEL: Record<PellierBadge, string> = {
  EDITORS_PICK: "EDITOR'S PICK",
  BESTSELLER: 'BESTSELLER',
  JUST_IN: 'JUST IN',
}

interface ProductCardProps {
  product: PellierProduct
  /** Row-wise index (0..2). Drives a compact per-column stagger. */
  index: number
  /** Optional `Add to bag` handler. The button is hidden when omitted. */
  onAddToBag?: (product: PellierProduct) => void
  /**
   * Optional provenance chips rendered under the reasoning chip. When
   * omitted, the card cites only catalog tags present on the product.
   */
  traces?: string[]
  /** Optional persona or surface accent used for provenance details. */
  accentColor?: string
  /** Larger, unframed storefront treatment. Detail-page siblings stay compact. */
  variant?: 'default' | 'editorial'
}

/**
 * Derive defensible provenance chips from committed catalog metadata.
 * Runtime tool claims must be supplied explicitly by a live response.
 */
function deriveTraces(product: PellierProduct): string[] {
  return product.tags.slice(0, 2).map(tag => `tag.match · ${tag}`)
}


// Per-column stagger in ms. Columns within a row play at 0ms, 50ms, 100ms so
// the catalog settles quickly while retaining a subtle left-to-right sweep. We use
// `index % 3` so the card computes the correct 0..2 column regardless of
// whether the grid passes a row-local or catalog-global index. At 92+ products
// a linear index-based cascade would push later cards well beyond a useful delay,
// well past the observer's attention window.
const STAGGER_MS = 50

// Columns per row in the desktop grid. The stagger math uses the widest case
// so the sweep is consistent on desktop; on narrower breakpoints the same
// modulo still reads as a small cascade.
const GRID_COLUMNS = 3

// Hard safety limit for the stuck-invisible bug that killed parallax v1. If
// the observer hasn't revealed the card within this window after mount, force
// the final state. 500ms is long enough to see a normal observer fire first.
const SAFETY_TIMEOUT_MS = 500

// Pre-reveal opacity. Keep this at 1 so a stalled observer never hides
// product content; the reveal still reads through a restrained transform.
const PRE_REVEAL_OPACITY = 1

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
  traces,
  accentColor,
  variant = 'default',
}: ProductCardProps) {
  const traceChips = traces ?? deriveTraces(product)
  const personaAccent = accentColor ?? 'var(--accent)'
  const editorial = variant === 'editorial'
  // Router `basename` prefixes this for the Workshop Studio /ports/8000/
  // proxy, so the path stays base-relative here.
  const detailPath = `/product/${product.id}`
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
        product-card group flex flex-col
        ${editorial
          ? 'product-card--editorial min-w-0'
          : `overflow-hidden rounded-[8px] border border-[rgba(24,26,31,0.10)]
             bg-cream-warm transition duration-fade ease-out
             hover:border-[rgba(24,26,31,0.20)] hover:shadow-warm-sm`}
      `}
      style={{
        '--trace-accent': personaAccent,
        opacity: isVisible ? 1 : PRE_REVEAL_OPACITY,
        transform: isVisible
          ? 'translateY(0) scale(1)'
          : 'translateY(12px) scale(0.99)',
        transition: `opacity 220ms ${REVEAL_EASE}, transform 260ms ${REVEAL_EASE}, box-shadow 180ms ease-out`,
      } as CSSProperties}
    >
      {/* --- Image panel ---------------------------------------------
       * The image and the product name both link to the piece's page. The
       * image link is a decorative duplicate: `aria-hidden` plus
       * `tabIndex={-1}` keeps it out of the accessibility tree and the tab
       * order, so assistive tech and keyboard users get exactly one link
       * per card while a pointer can still click the photograph.
       * ------------------------------------------------------------- */}
      <Link
        to={detailPath}
        aria-hidden="true"
        tabIndex={-1}
        className={`
          product-card-media relative block aspect-[4/5] overflow-hidden rounded-[var(--pellier-image-radius-md)] bg-sand
        `}
      >
        <ResponsiveImage
          src={product.imageUrl}
          alt={product.name}
          widths={[480, 960]}
          sizes={
            editorial
              ? '(min-width: 1180px) 33vw, (min-width: 700px) 50vw, 100vw'
              : '(min-width: 1280px) 320px, (min-width: 768px) 40vw, 100vw'
          }
          loading="lazy"
          decoding="async"
          pictureClassName="block h-full w-full"
          className="product-card-image h-full w-full object-cover transition-transform duration-200 ease-out"
          style={{
            objectPosition: product.imagePosition ?? 'center center',
          }}
        />
        {editorial ? (
          <span className="product-card-view">
            View piece
          </span>
        ) : null}
      </Link>

      {/* --- Text block ---------------------------------------------- */}
      <div className={`product-card-copy flex flex-col gap-3 ${editorial ? '' : 'p-5'}`}>
        <div className="flex justify-between gap-3 font-sans text-[12px] text-ink-quiet">
          <span>{product.brand}</span>
          <span>{editorial ? String(product.id).padStart(2, '0') : product.color}</span>
        </div>

        <div>
          <h3 className="product-name text-espresso">
            <Link
              to={detailPath}
              data-testid={`product-card-link-${product.id}`}
              className="
                inline-flex min-h-[44px] items-center
                transition-colors duration-fade hover:text-accent-ink
                focus-visible:outline-2 focus-visible:outline-offset-2
                focus-visible:outline-accent
              "
            >
              {product.name}
            </Link>
          </h3>
          <div className="mt-1.5 flex items-center gap-2 font-sans text-[12px] text-ink-quiet">
            <span>{editorial ? product.color : product.category}</span>
            {product.badge ? (
              <>
                <span aria-hidden="true">/</span>
                <span
                  data-testid={`product-card-badge-${product.id}`}
                  className="font-medium tracking-[0.04em] text-espresso"
                >
                  {BADGE_LABEL[product.badge]}
                </span>
              </>
            ) : null}
          </div>
        </div>

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

        {(product.reasoning || traceChips.length > 0) && (
          <details
            data-testid={`product-card-details-${product.id}`}
            className="group/details border-t border-sand pt-3"
          >
            <summary
              className="
                flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-3
                font-sans text-[12px] font-medium text-ink-soft
                focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-accent
              "
            >
              <span>Why this piece</span>
              <ChevronDown
                aria-hidden="true"
                className="h-4 w-4 transition-transform group-open/details:rotate-180"
                strokeWidth={1.8}
              />
            </summary>
            <div className="mt-3 flex flex-col gap-3">
              {product.reasoning ? <ReasoningChip chip={product.reasoning} /> : null}
              {traceChips.length > 0 ? (
                <div
                  data-testid={`product-card-traces-${product.id}`}
                  className="flex flex-wrap gap-1.5"
                  aria-label="Recommendation signals"
                >
                  {/* `signal` prints the tag itself. The friendly `label`
                      mode resolves every `tag.match` entry to one vocabulary
                      label, so two chips citing different tags both read
                      "Category match"; `tool` mode prints the internal signal
                      name, which is provenance for the Observatory, not for a
                      shopper. */}
                  {traceChips.map((trace) => (
                    <TraceChip
                      key={trace}
                      tool={trace}
                      variant="provenance"
                      labelMode="signal"
                      compact
                    />
                  ))}
                </div>
              ) : null}
            </div>
          </details>
        )}

        {onAddToBag ? (
          <button
            type="button"
            data-testid={`product-card-add-${product.id}`}
            onClick={() => onAddToBag(product)}
            className="
              mt-1 h-12 min-h-12 w-full rounded-full bg-espresso text-cream-50 border border-espresso
              py-2.5 px-3.5 text-[13px] tracking-[0.06em] cursor-pointer
              font-sans font-medium transition-colors duration-fade ease-out
              hover:bg-dusk hover:text-cream-50 hover:border-dusk
              focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent
            "
          >
            Add to bag
          </button>
        ) : null}
      </div>
    </article>
  )
}
