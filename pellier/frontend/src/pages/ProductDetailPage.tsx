import { apiFetch } from '../services/apiBase'
/**
 * ProductDetailPage — the `/product/:productId` route.
 *
 * A real route rather than a modal, so a piece can be linked, opened in a
 * new tab, and shared. The existing `UIContext.activeModal` singleton keeps
 * coordinating the concierge, cart, and comparison overlays; product detail
 * is a destination, not an overlay.
 *
 * The product detail and its related pieces come from Aurora. A failed
 * catalog read is explicit; this page never swaps in a committed browser
 * entry because its price, stock, and availability may be stale.
 *
 * No fabrication rules for this surface: product copy comes from the
 * catalog or is absent; stock comes from the inventory read or is declared
 * unread; the reasoning chip and provenance chips are the same committed
 * catalog metadata the grid card cites. Nothing here invents a material, a
 * delivery date, a review, or an agent step.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Sparkles, Star, X } from 'lucide-react'

import AnnouncementBar from '../components/AnnouncementBar'
import Footer from '../components/Footer'
import Header, { type NavItem } from '../components/Header'
import ProductAvailabilityPanel from '../components/ProductAvailabilityPanel'
import ProductCard from '../components/ProductCard'
import { asset } from '../utils/assetPath'
import ReasoningChip from '../components/ReasoningChip'
import ResponsiveImage from '../components/ResponsiveImage'
import { TraceChip } from '../shared'
import { useFocusTrap } from '../shared/useFocusTrap'
import { useCart } from '../contexts/CartContext'
import { useUI } from '../contexts/UIContext'
import { PRODUCT_DETAIL } from '../copy'
import type {
  PellierBadge,
  PellierProduct,
  PellierProductDetail,
  ProductAvailability,
} from '../services/types'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/',
  shop: '/#shop',
  storyboard: '/storyboard',
  stories: '/storyboard',
  discover: '/discover',
  about: '/about',
  'how-it-works': '/how-pellier-works',
  account: '/',
  'ask-pellier': '/',
}

const BADGE_LABEL: Record<PellierBadge, string> = {
  EDITORS_PICK: "EDITOR'S PICK",
  BESTSELLER: 'BESTSELLER',
  JUST_IN: 'JUST IN',
}

/** Siblings shown under "More from this edit". */
const SIBLING_COUNT = 3

/**
 * What the page renders. Presentation fields only — `description` and
 * `availability` stay separate because they have their own provenance and
 * their own degraded states.
 */
interface ProductView {
  id: number
  brand: string
  name: string
  color: string
  price: number
  rating: number
  reviewCount: number
  category: string
  imageUrl: string
  badge?: PellierBadge
  tags: string[]
  reasoning?: PellierProduct['reasoning']
  imagePosition?: string
}

function viewFromRemote(detail: PellierProductDetail): ProductView {
  return {
    id: detail.id,
    brand: detail.brand,
    name: detail.name,
    color: detail.color,
    price: detail.price,
    rating: detail.rating,
    reviewCount: detail.reviewCount,
    category: detail.category,
    imageUrl: detail.imageUrl,
    badge: detail.badge ?? undefined,
    tags: detail.tags,
  }
}

/**
 * Provenance chips over committed catalog tags — the same derivation
 * `ProductCard` uses, so the card and the page cite identical signals.
 */
function catalogSignals(tags: string[]): string[] {
  return tags.slice(0, 4).map(tag => `tag.match · ${tag}`)
}

export default function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>()
  const [zoomOpen, setZoomOpen] = useState(false)
  const zoomRef = useRef<HTMLDivElement>(null)
  useFocusTrap({ containerRef: zoomRef, active: zoomOpen, onClose: () => setZoomOpen(false) })
  useEffect(() => {
    if (!zoomOpen) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [zoomOpen])
  const navigate = useNavigate()
  const { addToCart } = useCart()
  const { openModal, openDrawerWithQuery, setChatSurface } = useUI()

  const numericId = Number(productId)
  const hasValidId = /^\d+$/.test(productId ?? '') && Number.isSafeInteger(numericId) && numericId > 0

  const [detail, setDetail] = useState<PellierProductDetail | null>(null)
  const [catalog, setCatalog] = useState<PellierProduct[]>([])
  const [loading, setLoading] = useState(hasValidId)
  const [loadError, setLoadError] = useState(false)
  const [retryVersion, setRetryVersion] = useState(0)

  useEffect(() => {
    setChatSurface('drawer')
  }, [setChatSurface])

  useEffect(() => {
    document.body.classList.add('pellier-surface')
    return () => document.body.classList.remove('pellier-surface')
  }, [])

  useEffect(() => {
    setZoomOpen(false)
    window.scrollTo({ top: 0 })
  }, [numericId])

  // Every other route in the app (Observatory, Operator, and
  // HowPellierWorksPage) sets a specific document title; this route and
  // the two below kept the generic index.html default the whole time the
  // shopper was reading a specific piece, which loses the product identity
  // in a browser tab or a screen reader's tab list. Falls back to the
  // default title (restored on unmount) while the product hasn't loaded
  // yet or failed to load, since a stale "Pellier" tab is honest and an
  // invented product name is not.
  useEffect(() => {
    if (!detail) return
    const previous = document.title
    document.title = `${detail.name} | Pellier`
    return () => { document.title = previous }
  }, [detail])

  useEffect(() => {
    setLoadError(false)
    setCatalog([])
    if (!hasValidId) {
      setDetail(null)
      setLoading(false)
      return
    }
    let active = true
    const controller = new AbortController()
    setLoading(true)
    setDetail(null)
    void apiFetch(`/api/products/${numericId}`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 404) return null
        if (!response.ok) throw new Error('Product read unavailable')
        return await response.json() as PellierProductDetail
      })
      .then((data) => { if (active) setDetail(data) })
      .catch(() => { if (active) setLoadError(true) })
      .finally(() => { if (active) setLoading(false) })

    // Related pieces are optional. Their read must not block or hide a
    // successfully loaded product, price, or availability receipt.
    void apiFetch('/api/products', {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Related collection unavailable')
        return await response.json() as PellierProduct[]
      })
      .then((products) => { if (active) setCatalog(products) })
      .catch(() => { if (active) setCatalog([]) })
    return () => {
      active = false
      controller.abort()
    }
  }, [hasValidId, numericId, retryVersion])

  const view: ProductView | null = useMemo(() => {
    if (detail) return viewFromRemote(detail)
    return null
  }, [detail])

  const siblings = useMemo(() => {
    if (!view) return []
    return catalog
      .filter(p => p.id !== view.id)
      .slice(0, SIBLING_COUNT)
  }, [catalog, view])

  const handleNavigate = (item: NavItem) => {
    if (item === 'account') {
      openModal('auth')
      return
    }
    if (item === 'ask-pellier') {
      openModal('drawer')
      return
    }
    const target = NAV_ROUTES[item]
    if (target) navigate(target)
  }

  const handleAddToBag = (product: { id: number; name: string; price: number; imageUrl: string }) =>
    addToCart({
      productId: product.id,
      name: product.name,
      price: product.price,
      image: product.imageUrl,
      origin: 'manual',
    })

  // Still reading, and nothing committed to paint from: hold the frame
  // rather than briefly claiming the piece does not exist.
  if (!view && loading) {
    return (
      <div className="pellier-page-surface flex min-h-dvh flex-col bg-cream-50">
        <Header current="shop" onNavigate={handleNavigate} />
        <main
          role="status"
          aria-label="Loading"
          className="flex flex-1 items-center justify-center bg-cream"
        >
          <span className="h-7 w-7 animate-spin rounded-full border-2 border-black/10 border-t-black/50" />
        </main>
        <Footer />
      </div>
    )
  }

  if (!view) {
    return (
      <div
        data-testid={loadError ? 'product-detail-unavailable' : 'product-detail-not-found'}
        className="pellier-page-surface flex min-h-dvh flex-col bg-cream-50"
      >
        <Header current="shop" onNavigate={handleNavigate} />
        <main className="flex-1 bg-cream">
          <div className="mx-auto max-w-[720px] px-container-x py-24 text-center" role={loadError ? 'alert' : undefined}>
            <h1
              className="font-display text-espresso"
              style={{ fontSize: 'clamp(28px, 4vw, 44px)', lineHeight: 1.15 }}
            >
              {loadError ? PRODUCT_DETAIL.UNAVAILABLE_TITLE : PRODUCT_DETAIL.NOT_FOUND_TITLE}
            </h1>
            <p className="mt-4 font-sans text-ink-soft">
              {loadError ? PRODUCT_DETAIL.UNAVAILABLE_BODY : PRODUCT_DETAIL.NOT_FOUND_BODY}
            </p>
            {loadError ? (
              <div className="mt-6">
                <button type="button" className="pellier-retry" onClick={() => setRetryVersion(v => v + 1)}>
                  Try again
                </button>
              </div>
            ) : null}
            <Link
              to="/#shop"
              className="
                mt-8 inline-flex items-center gap-2 rounded-full bg-espresso
                px-7 py-3 font-sans text-[13px] font-medium text-cream-50
                transition-colors duration-fade hover:bg-dusk
              "
            >
              <ArrowLeft size={15} aria-hidden="true" />
              {PRODUCT_DETAIL.NOT_FOUND_ACTION}
            </Link>
          </div>
        </main>
        <Footer />
      </div>
    )
  }

  const availability: ProductAvailability | null = detail?.availability ?? null
  const description = detail?.description?.trim() || null
  const signals = catalogSignals(view.tags)

  return (
    <div data-testid="product-detail-page" className="pellier-page-surface min-h-dvh bg-cream-50">
      <AnnouncementBar />
      <Header current="shop" onNavigate={handleNavigate} />

      <main className="bg-cream">
        <nav
          aria-label="Breadcrumb"
          className="mx-auto max-w-[1200px] px-container-x pt-6 font-sans text-[12px] text-ink-quiet"
        >
          <ol className="flex flex-wrap items-center gap-2">
            <li>
              <Link to="/" className="transition-colors hover:text-espresso">
                {PRODUCT_DETAIL.BREADCRUMB_ROOT}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li>
              <Link to="/#shop" className="transition-colors hover:text-espresso">
                {view.category}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li aria-current="page" className="text-espresso">
              {view.name}
            </li>
          </ol>
        </nav>

        <div className="mx-auto max-w-[1200px] px-container-x pb-16 pt-8 md:pb-24">
          <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[minmax(0,520px)_minmax(0,1fr)] lg:gap-16 xl:gap-20">
            {/* --- Piece ------------------------------------------------ */}
            <div className="overflow-hidden rounded-[var(--pellier-image-radius-lg)] border border-sand bg-sand">
              {/* One photograph per piece today. A zoom is the honest version
                  of a gallery until more angles exist: the shopper can still
                  look closely at the weave before paying for it. */}
              <button
                type="button"
                className="relative block aspect-[4/5] w-full cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-espresso focus-visible:ring-offset-2"
                aria-label={`Zoom in on ${view.name}`}
                data-testid="product-detail-zoom"
                onClick={() => setZoomOpen(true)}
              >
                <ResponsiveImage
                  src={view.imageUrl}
                  alt={view.name}
                  widths={[480, 960]}
                  sizes="(min-width: 1200px) 520px, (min-width: 1024px) 44vw, 100vw"
                  loading="eager"
                  decoding="async"
                  pictureClassName="block h-full w-full"
                  className="h-full w-full object-cover"
                  style={{ objectPosition: view.imagePosition ?? 'center center' }}
                />
              </button>
            </div>
            {zoomOpen ? (
              <div
                ref={zoomRef}
                role="dialog"
                aria-modal="true"
                aria-label={`${view.name}, enlarged`}
                data-testid="product-detail-zoom-dialog"
                className="fixed inset-0 z-[1200] flex items-center justify-center bg-[rgba(45,24,16,0.86)] p-6"
                onClick={() => setZoomOpen(false)}
              >
                <img
                  src={asset(view.imageUrl)}
                  alt={view.name}
                  className="max-h-[92vh] max-w-[92vw] rounded-[var(--pellier-image-radius-lg)] object-contain shadow-warm-md"
                  onClick={(event) => event.stopPropagation()}
                />
                <button
                  type="button"
                  className="absolute right-6 top-6 inline-flex h-11 w-11 items-center justify-center rounded-full bg-cream-50 text-espresso focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cream-50"
                  aria-label="Close enlarged image"
                  onClick={() => setZoomOpen(false)}
                >
                  <X size={18} strokeWidth={1.8} aria-hidden="true" />
                </button>
              </div>
            ) : null}

            {/* --- Detail ---------------------------------------------- */}
            <div
              data-testid="product-detail-summary"
              className="flex flex-col gap-6 lg:pt-2"
            >
              <div>
                <p className="font-sans text-[12px] uppercase tracking-[0.14em] text-ink-quiet">
                  {view.brand}
                </p>
                <h1
                  data-testid="product-detail-name"
                  className="mt-2 font-display pellier-product-title text-espresso"
                  style={{ fontSize: 'clamp(30px, 3.6vw, 48px)', lineHeight: 1.1 }}
                >
                  {view.name}
                </h1>
                <div className="mt-3 flex flex-wrap items-center gap-2 font-sans text-[13px] text-ink-quiet">
                  <span>{view.color}</span>
                  <span aria-hidden="true">/</span>
                  <span>{view.category}</span>
                  {view.badge ? (
                    <>
                      <span aria-hidden="true">/</span>
                      <span
                        data-testid="product-detail-badge"
                        className="font-medium text-accent-ink"
                      >
                        {BADGE_LABEL[view.badge]}
                      </span>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="flex items-center gap-4 border-y border-sand py-4 font-sans">
                <span className="text-xl text-espresso">${view.price}</span>
                <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
                  <Star
                    size={13}
                    strokeWidth={1.5}
                    aria-hidden="true"
                    className="fill-ink-soft text-ink-soft"
                  />
                  {view.rating.toFixed(1)}
                  <span className="text-xs text-ink-quiet">({view.reviewCount})</span>
                </span>
              </div>

              {/* Catalog copy, or an explicit statement that it was not read. */}
              <section aria-labelledby="product-description-heading">
                <h2
                  id="product-description-heading"
                  className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-soft"
                >
                  {PRODUCT_DETAIL.DESCRIPTION_HEADING}
                </h2>
                {description ? (
                  <p
                    data-testid="product-description"
                    className="mt-3 max-w-[52ch] font-sans text-[15px] leading-relaxed text-ink-soft"
                  >
                    {description}
                  </p>
                ) : (
                  <p
                    data-testid="product-description-degraded"
                    className="mt-3 font-sans text-[13px] text-ink-quiet"
                  >
                    {loading
                      ? PRODUCT_DETAIL.AVAILABILITY_READING
                      : PRODUCT_DETAIL.DESCRIPTION_UNAVAILABLE}
                  </p>
                )}
              </section>

              <ProductAvailabilityPanel
                availability={availability}
                loading={loading}
              />

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <button
                  type="button"
                  data-testid="product-detail-add"
                  onClick={() => handleAddToBag(view)}
                  className="pellier-action min-w-[200px] flex-1"
                >
                  {PRODUCT_DETAIL.ADD_TO_BAG}
                </button>
                <button
                  type="button"
                  data-testid="product-detail-ask"
                  onClick={() => openDrawerWithQuery(PRODUCT_DETAIL.askQuestion(view.name))}
                  className="
                    inline-flex min-h-[46px] items-center justify-center gap-2
                    rounded-full border border-sand bg-cream-warm px-5
                    font-sans text-[13px] font-medium text-ink-soft
                    transition-colors duration-fade hover:border-ink-quiet/40
                    hover:bg-sand/60 hover:text-espresso
                    focus-visible:outline-2 focus-visible:outline-offset-2
                    focus-visible:outline-accent
                  "
                >
                  <Sparkles
                    className="pellier-concierge-sparkle"
                    size={15}
                    aria-hidden="true"
                  />
                  {PRODUCT_DETAIL.ASK_LABEL}
                </button>
              </div>

              {view.reasoning ? (
                <section aria-labelledby="product-why-heading">
                  <h2
                    id="product-why-heading"
                    className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-soft"
                  >
                    {PRODUCT_DETAIL.WHY_HEADING}
                  </h2>
                  <div className="mt-3">
                    <ReasoningChip chip={view.reasoning} />
                  </div>
                </section>
              ) : null}

              {signals.length > 0 ? (
                <section aria-labelledby="product-signals-heading">
                  <h2
                    id="product-signals-heading"
                    className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-soft"
                  >
                    {PRODUCT_DETAIL.SIGNALS_HEADING}
                  </h2>
                  <div
                    data-testid="product-detail-signals"
                    className="mt-3 flex flex-wrap gap-1.5"
                  >
                    {/* `signal` prints the tag itself. The friendly `label`
                        mode resolves every `tag.match` entry to the same
                        vocabulary label, which would render four identical
                        chips; `tool` mode prints the internal signal name,
                        which belongs in the Observatory, not on a piece. */}
                    {signals.map(signal => (
                      <TraceChip
                        key={signal}
                        tool={signal}
                        variant="provenance"
                        labelMode="signal"
                        compact
                      />
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          </div>
        </div>

        {siblings.length > 0 ? (
          <section
            aria-labelledby="product-more-heading"
            className="border-t border-sand bg-cream-warm"
          >
            <div className="mx-auto max-w-[1280px] px-container-x py-16">
              <h2
                id="product-more-heading"
                className="font-display text-espresso"
                style={{ fontSize: 'clamp(24px, 2.6vw, 34px)', lineHeight: 1.15 }}
              >
                {PRODUCT_DETAIL.MORE_HEADING}
              </h2>
              <div
                data-testid="product-detail-siblings"
                className="mt-8 grid gap-6"
                style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}
              >
                {siblings.map((product, index) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    index={index % 3}
                    onAddToBag={handleAddToBag}
                  />
                ))}
              </div>
            </div>
          </section>
        ) : null}
      </main>

      <Footer />
    </div>
  )
}
