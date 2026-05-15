/**
 * HeroStage — the cinematic hero that cycles through 8 shopper intents.
 *
 * Validates Requirements 1.3.1 through 1.3.10.
 *
 * Behavior highlights:
 *  - Cross-fades through the 8 intents from `copy.ts`, advancing every 7.5s.
 *  - Intent 2 ("a thoughtful gift for someone who runs") renders the
 *    `productOverride` (Featherweight Trail Runner) instead of a catalog
 *    lookup.
 *  - Hover anywhere on the stage pauses rotation, freezes the progress bar
 *    at its current fill, and leaves ticker chips clickable.
 *  - Unhover resumes from the paused position (not restart).
 *  - Ticker chip click jumps to that intent and resets the 7.5s timer.
 *  - Search pill keyword-match on Enter jumps to the matched intent.
 *  - `slow-zoom` Ken Burns animation (14s alternate, 1.02 → 1.08) is
 *    applied to the active image.
 *  - Mobile (<768px) shows the dark glass breadcrumb top-left; desktop
 *    hides it and shows the cream "Curated for you" chip top-right.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  INTENTS,
  HERO_BREADCRUMB,
  CURATED_FOR_YOU_CHIP,
  OTHERS_ARE_ASKING_LABEL,
  type Intent,
} from '../copy'
import { SHOWCASE_PRODUCTS } from '../data/showcaseProducts'
import { useUI } from '../contexts/UIContext'

// Rotation cadence (Req 1.3.1).
const INTENT_INTERVAL_MS = 7500

// Progress bar refresh cadence. 60 ms gives smooth movement without taxing
// the event loop; the math always uses real elapsed time, so the rate is only
// a "how often do we re-render" knob.
const PROGRESS_TICK_MS = 60

// --- Resolution helpers -------------------------------------------------

/**
 * Shape the IntentInfoCard consumes. Intent productOverride is used verbatim
 * when present; otherwise we synthesize a minimal display record from the
 * productRef name so the card still renders while the real catalog lookup is
 * pending elsewhere.
 */
interface DisplayProduct {
  name: string
  brand: string
  color: string
  price: number
  rating: number
  reviewCount: number
  reviews?: string
  imageUrl: string
}

function resolveProduct(intent: Intent): DisplayProduct {
  if (intent.productOverride) {
    return intent.productOverride
  }
  // productRef -> look up the matching showcase card by name so the hero
  // reuses the catalog's curated Unsplash URL and price/rating. Falling back
  // to a slugged local path here caused 404s in the most visible surface on
  // the page when a JPG was missing from /public/images/.
  const name = intent.productRef?.name ?? 'Curated piece'
  const match = SHOWCASE_PRODUCTS.find(p => p.name === name)
  if (match) {
    return {
      name: match.name,
      brand: match.brand,
      color: match.color,
      price: match.price,
      rating: match.rating,
      reviewCount: match.reviewCount,
      imageUrl: match.imageUrl,
    }
  }
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
  return {
    name,
    brand: 'Pellier Editions',
    color: '',
    price: 0,
    rating: 0,
    reviewCount: 0,
    imageUrl: `/images/${slug}.jpg`,
  }
}

// --- Subcomponents ------------------------------------------------------

interface IntentInfoCardProps {
  intent: Intent
  product: DisplayProduct
}

export function IntentInfoCard({ intent, product }: IntentInfoCardProps) {
  // Keying the wrapper on intent.id forces the cascade-in animations to
  // replay every time the active intent changes (rather than only on mount).
  return (
    <div
      key={intent.id}
      data-testid="intent-info-card"
      className="pointer-events-auto absolute left-5 top-5 z-20 w-[clamp(260px,30%,380px)] rounded-3xl bg-cream-50/95 p-5 shadow-warm-xl ring-1 ring-espresso/5 backdrop-blur-md md:left-6 md:top-6 md:p-6"
    >
      {/* Breadcrumb with small B mark + pulse dot (Req 1.3.4) */}
      <div
        data-testid="info-card-breadcrumb"
        className="cascade-in mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-ink-soft"
        style={{ ['--cascade-delay' as string]: '0s' }}
      >
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-espresso font-[Fraunces] text-[10px] text-cream-50">
          B
        </span>
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
        </span>
        <span>{HERO_BREADCRUMB}</span>
      </div>

      {/* Intent query in italic Fraunces, wrapped in curly quotes (Req 1.3.4) */}
      <p
        data-testid="intent-query"
        className="cascade-in mb-4 font-[Fraunces] text-[22px] italic leading-snug text-espresso md:text-[26px]"
        style={{ ['--cascade-delay' as string]: '0.1s' }}
      >
        &ldquo;{intent.query}&rdquo;
      </p>

      {/* Product details row */}
      <div
        className="cascade-in mb-4 text-[13px] text-ink-soft"
        style={{ ['--cascade-delay' as string]: '0.2s' }}
      >
        <span className="mr-2 uppercase tracking-wider">{product.brand}</span>
        {product.color ? <span className="mr-2">&middot; {product.color}</span> : null}
        <div className="mt-1 font-[Fraunces] text-[17px] text-espresso md:text-[19px]">
          {product.name}
        </div>
        <div className="mt-1 flex items-center gap-2 text-[13px]">
          {product.price > 0 ? <span>${product.price}</span> : null}
          {product.rating > 0 ? (
            <>
              <span className="text-accent">&#9733;</span>
              <span>{product.rating.toFixed(1)}</span>
              <span className="text-ink-quiet">
                ({product.reviews ?? product.reviewCount})
              </span>
            </>
          ) : null}
        </div>
      </div>

      {/* Action row: Add to bag + heart */}
      <div
        className="cascade-in mb-4 flex items-center gap-3"
        style={{ ['--cascade-delay' as string]: '0.3s' }}
      >
        <button
          type="button"
          className="flex-1 rounded-full bg-espresso px-5 py-2 text-sm font-medium text-cream-50 transition-colors duration-fade hover:bg-dusk"
        >
          Add to bag
        </button>
        <button
          type="button"
          aria-label="Save to wishlist"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-espresso/20 text-espresso transition-colors duration-fade hover:bg-sand"
        >
          &#9825;
        </button>
      </div>

      <div className="mb-3 h-px bg-espresso/10" />

      {/* 10px mono footnote (Req 1.3.4) */}
      <div
        data-testid="matched-on"
        className="cascade-in flex items-center justify-between text-[10px] text-ink-quiet"
        style={{
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          ['--cascade-delay' as string]: '0.3s',
        }}
      >
        <span>Matched on: {intent.matchedOn.join(' \u00b7 ')}</span>
        <span data-testid="latency-stamp">{intent.latency}</span>
      </div>
    </div>
  )
}

interface IntentTickerProps {
  intents: Intent[]
  activeIndex: number
  onSelect: (index: number) => void
  /** Opens the chat drawer with this intent's query already streaming. */
  onOpenDrawer?: (query: string) => void
}

export function IntentTicker({ intents, activeIndex, onSelect, onOpenDrawer }: IntentTickerProps) {
  return (
    <div
      data-testid="intent-ticker"
      className="pointer-events-auto flex flex-wrap items-center gap-3 px-6 py-3"
    >
      <span
        data-testid="intent-ticker-label"
        className="flex shrink-0 items-center gap-2 whitespace-nowrap text-[10px] font-medium uppercase tracking-[0.2em] text-ink-quiet font-[Inter]"
      >
        <span className="relative flex h-1.5 w-1.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
        </span>
        {OTHERS_ARE_ASKING_LABEL}
      </span>
      {intents.map((intent, i) => {
        const selected = i === activeIndex
        return (
          <button
            key={intent.id}
            type="button"
            data-testid={`ticker-chip-${i}`}
            data-active={selected}
            onClick={() => {
              onSelect(i)
              onOpenDrawer?.(intent.query)
            }}
            className={
              'shrink-0 border text-[11px] italic transition-colors ' +
              (selected
                ? 'border-ink bg-ink not-italic text-cream-warm'
                : 'border-ink-quiet/20 bg-cream-warm text-ink-quiet hover:border-ink')
            }
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              borderRadius: 12,
              padding: '10px 18px',
            }}
          >
            &ldquo;{intent.query}&rdquo;
          </button>
        )
      })}
    </div>
  )
}

interface ProgressBarProps {
  percent: number // 0..100
}

export function ProgressBar({ percent }: ProgressBarProps) {
  return (
    <div
      data-testid="progress-bar"
      className="h-[2px] w-full bg-espresso/10"
    >
      <div
        data-testid="progress-bar-fill"
        className="h-full bg-accent transition-[width] duration-75 ease-linear"
        style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
      />
    </div>
  )
}

// --- Keyword match helper ----------------------------------------------

/**
 * Returns the index of the first intent whose query or matchedOn tags contain
 * any whitespace-delimited token from `query`. Case-insensitive. Returns -1
 * on no match. Exported for unit testing without needing to mount the stage.
 */
export function matchIntent(query: string, intents: Intent[]): number {
  const tokens = query
    .toLowerCase()
    .split(/\s+/)
    .map(t => t.trim())
    .filter(t => t.length >= 3) // ignore short connectives like "a", "of"
  if (tokens.length === 0) return -1

  for (let i = 0; i < intents.length; i++) {
    const haystack = (
      intents[i].query +
      ' ' +
      intents[i].matchedOn.join(' ')
    ).toLowerCase()
    if (tokens.some(t => haystack.includes(t))) {
      return i
    }
  }
  return -1
}

// --- HeroStage ----------------------------------------------------------

interface HeroStageProps {
  /**
   * Override for tests; production uses the 8 intents from `copy.ts`.
   */
  intents?: Intent[]
}

export default function HeroStage({ intents = INTENTS }: HeroStageProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [hovering, setHovering] = useState(false)

  // Image cross-fade state (storefront mock parity). When the active intent
  // changes we dip the image to 0.25 opacity, swap `src` at the midpoint, and
  // restore to 1 — giving a 500ms softened swap instead of a hard pop.
  const [displayedIndex, setDisplayedIndex] = useState(0)
  const [imageOpacity, setImageOpacity] = useState(1)
  useEffect(() => {
    if (displayedIndex === activeIndex) return
    setImageOpacity(0.25)
    const midpoint = window.setTimeout(() => {
      setDisplayedIndex(activeIndex)
      setImageOpacity(1)
    }, 250)
    return () => window.clearTimeout(midpoint)
  }, [activeIndex, displayedIndex])

  // Progress bar state expressed as an absolute percent to avoid drift.
  const [progressPercent, setProgressPercent] = useState(0)

  // The "world-clock" anchor: the timestamp when the current 7.5s window
  // started. Hovering subtracts the hover time so unhover resumes where we
  // paused (Req 1.3.7). Jump/reset replaces the anchor with `now` (Req 1.3.8).
  const cycleStartRef = useRef<number>(Date.now())
  const pausedElapsedRef = useRef<number>(0) // frozen percent in ms when hover started
  const hoverStartedAtRef = useRef<number | null>(null)

  // Recompute progress + advance intent on a tick.
  const tick = useCallback(() => {
    if (hoverStartedAtRef.current !== null) {
      // While hovering we do NOT advance the anchor. Progress stays where it
      // was when hover started (Req 1.3.6).
      const frozenPercent = (pausedElapsedRef.current / INTENT_INTERVAL_MS) * 100
      setProgressPercent(frozenPercent)
      return
    }
    const elapsed = Date.now() - cycleStartRef.current
    if (elapsed >= INTENT_INTERVAL_MS) {
      // Advance to the next intent and reset the cycle anchor.
      cycleStartRef.current = Date.now()
      setProgressPercent(0)
      setActiveIndex(prev => (prev + 1) % intents.length)
      return
    }
    setProgressPercent((elapsed / INTENT_INTERVAL_MS) * 100)
  }, [intents.length])

  useEffect(() => {
    const id = window.setInterval(tick, PROGRESS_TICK_MS)
    return () => window.clearInterval(id)
  }, [tick])

  // Hover pause/resume handlers (Req 1.3.6, 1.3.7).
  const handleMouseEnter = useCallback(() => {
    if (hoverStartedAtRef.current !== null) return
    hoverStartedAtRef.current = Date.now()
    pausedElapsedRef.current = Date.now() - cycleStartRef.current
    setHovering(true)
  }, [])

  const handleMouseLeave = useCallback(() => {
    if (hoverStartedAtRef.current === null) return
    // Shift the cycle anchor forward by the hover duration so `now - anchor`
    // matches the paused elapsed time; i.e. the progress resumes from where
    // it paused rather than restarting (Req 1.3.7).
    const hoverDuration = Date.now() - hoverStartedAtRef.current
    cycleStartRef.current += hoverDuration
    hoverStartedAtRef.current = null
    setHovering(false)
  }, [])

  // Jump to a specific intent and reset the 7.5s timer (Req 1.3.8, 1.3.9).
  const jumpTo = useCallback((index: number) => {
    if (index < 0 || index >= intents.length) return
    setActiveIndex(index)
    cycleStartRef.current = Date.now()
    pausedElapsedRef.current = 0
    // If the user was hovering when the jump fires, keep the pause state
    // consistent: the hover anchor is now.
    if (hoverStartedAtRef.current !== null) {
      hoverStartedAtRef.current = Date.now()
    }
    setProgressPercent(0)
  }, [intents.length])

  const { openDrawerWithQuery } = useUI()

  const activeIntent = intents[activeIndex]
  const activeProduct = useMemo(() => resolveProduct(activeIntent), [activeIntent])
  const displayedProduct = useMemo(
    () => resolveProduct(intents[displayedIndex]),
    [intents, displayedIndex],
  )

  return (
    <section
      data-testid="hero-stage"
      data-hovering={hovering}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className="relative mx-auto w-full max-w-[1440px] px-container-x pt-6"
      aria-label="Hero stage"
    >
      {/* Hero frame: rounded rectangle with the Ken Burns image. A subtle
          radial cream-warm gradient + a warm-tinted drop shadow give the
          card the magazine-spread lift called for in the mock. The ticker
          strip is a sibling inside this wrapper so its bottom edge follows
          the wrapper's rounded corners — mock parity. */}
      <div
        data-testid="hero-frame"
        className="relative overflow-hidden rounded-3xl shadow-warm-md"
        style={{
          background:
            'radial-gradient(120% 120% at 50% 50%, rgba(232,223,212,0) 0%, rgba(232,223,212,0.85) 70%, rgba(232,223,212,1) 100%), #E8DFD4',
        }}
      >
        {/* The image panel must clip its own contents — the Ken Burns
            zoom animates the <img> from scale 1.02 → 1.08, and without
            ``overflow-hidden`` here the scaled image bleeds DOWN onto
            the "Others are asking" ticker strip that sits as a sibling
            inside the same hero-frame. The hero-frame's overflow-
            hidden handles the outer edge but not sibling overlap. */}
        <div
          data-testid="hero-stage-image-panel"
          className="relative aspect-[4/3] md:aspect-[2/1] overflow-hidden"
        >
          {/* Mobile-only dark glass breadcrumb top-left (Req 1.3.10) */}
          <div
            data-testid="mobile-breadcrumb"
            className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-full bg-espresso/70 px-3 py-1 text-[11px] text-cream-50 backdrop-blur-md md:hidden"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
            <span>{HERO_BREADCRUMB}</span>
          </div>

          {/* Desktop-only cream "Curated for you" chip top-right (Req 1.3.10) */}
          <div
            data-testid="desktop-curated-chip"
            className="absolute right-4 top-4 z-10 hidden rounded-full bg-cream-50/85 px-3 py-1 text-[11px] uppercase tracking-[0.12em] text-espresso backdrop-blur-md md:block"
          >
            {CURATED_FOR_YOU_CHIP}
          </div>

          {/* Active image with slow-zoom Ken Burns (Req 1.3.2). A tween on the
              opacity gives the 500ms crossfade when the active intent changes;
              the src is swapped at the midpoint via `displayedIndex`. */}
          <img
            data-testid="hero-image"
            src={displayedProduct.imageUrl}
            alt={displayedProduct.name}
            className="hero-stage-image h-full w-full object-cover"
            style={{
              opacity: imageOpacity,
              transition: 'opacity 250ms ease-out',
              objectPosition: 'center 80%',
            }}
          />

          {/* Info card floats over the image on desktop; stacks below on mobile. */}
          <IntentInfoCard intent={activeIntent} product={activeProduct} />
        </div>

        {/* Progress bar + ticker strip as a sibling of the image panel so
            the strip attaches to the bottom of the hero card. White
            background + warm-tinted top border separate it visually from
            the image while keeping the single rounded unit. */}
        <div
          data-testid="hero-stage-ticker-strip"
          className="bg-white border-t border-warm"
        >
          <ProgressBar percent={progressPercent} />
          <IntentTicker
            intents={intents}
            activeIndex={activeIndex}
            onSelect={jumpTo}
            onOpenDrawer={openDrawerWithQuery}
          />
        </div>
      </div>
    </section>
  )
}
