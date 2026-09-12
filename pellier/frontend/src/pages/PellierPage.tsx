/**
 * PellierPage — the `/` route composition (Pellier redesign).
 *
 * Two-act layout:
 *
 *   ACT 1 (above the fold — full viewport):
 *     Header (sticky) → PellierHero (full-height search surface)
 *
 *   ACT 2 (below the fold — scroll to discover):
 *     Featured product image (weekender bag) + "Weekend, re:defined."
 *     → full nine-piece guest edit, or 9 remaining persona products
 *     → "Because you asked..." editorial cards
 *     → Footer
 *
 * The hero occupies the entire viewport so the first impression is
 * the search bar. Scrolling reveals the editorial product showcase.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Header, { type NavItem } from '../components/Header'
import PellierHero from '../components/PellierHero'
import PellierApproach from '../components/PellierApproach'
import PellierServiceStrip from '../components/PellierServiceStrip'
import RationaleBand from '../components/RationaleBand'
import ProductCard from '../components/ProductCard'
import ResponsiveImage from '../components/ResponsiveImage'
import Footer from '../components/Footer'
import PellierSpotlight from '../components/PellierSpotlight'
import OperatorClientPreview from '../components/OperatorClientPreview'
// CommandPill removed — hero search bar is the primary entry point
import { useAuth } from '../contexts/AuthContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import {
  PERSONA_INTERESTS,
  weekendEditForPersona,
} from '../data/personaCurations'
import type { PellierProduct } from '../services/types'
import { splitHeadlineAtRe } from '../utils/headlineAccent'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/',
  shop: '/#shop',
  storyboard: '/storyboard',
  stories: '/storyboard',
  discover: '/#shop',
  about: '/about',
  account: '/',
  'ask-pellier': '/',
}

export function selectStorefrontGridProducts(
  products: readonly PellierProduct[],
  personaId: string | null,
): readonly PellierProduct[] {
  return personaId ? products.slice(1) : products
}

// Featured product + grid are now persona-aware (computed inside component)

export default function PellierPage() {
  const { prefsVersion } = useAuth()
  const { openModal, setChatSurface } = useUI()
  const { addToCart } = useCart()
  const { persona, switchPersona, clearPersona } = usePersona()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const handledPersona = useRef<string | null>(null)

  const requestedPersona = searchParams.get('persona')?.trim().toLowerCase() ?? ''
  const clientPreviewId = searchParams.get('clientPreview')?.trim() ?? ''

  // A hero handoff is a real persona switch, not a decorative link. Consume
  // the query once so refresh does not mint a second shopper session.
  useEffect(() => {
    if (!requestedPersona || handledPersona.current === requestedPersona) return
    handledPersona.current = requestedPersona

    const next = new URLSearchParams(searchParams)
    next.delete('persona')
    setSearchParams(next, { replace: true })

    void switchPersona(requestedPersona)
  }, [requestedPersona, searchParams, setSearchParams, switchPersona])

  // A nonhero client preview must never inherit Marco, Anna, or Theo's
  // storefront state. This clears only the workshop persona/session state;
  // the httpOnly operator authorization cookie is untouched.
  useLayoutEffect(() => {
    if (clientPreviewId && persona) clearPersona()
  }, [clearPersona, clientPreviewId, persona])

  const personaId = persona?.id ?? null
  const [products, setProducts] = useState<PellierProduct[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogRevision, setCatalogRevision] = useState(0)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  // The home edit is an Aurora grouping created by migration 029. Do not
  // retain a browser catalog when the active profile changes: a stale row is
  // worse than a visible unavailable state in a workshop about grounding.
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const profile = personaId ?? 'fresh'
    setCatalogLoading(true)
    setCatalogError(null)
    setProducts([])

    void fetch(`/api/products?persona=${encodeURIComponent(profile)}`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) {
          throw new Error(`Live catalog request failed: ${response.status}`)
        }
        return response.json() as Promise<PellierProduct[]>
      })
      .then(catalog => {
        if (!active) return
        if (!Array.isArray(catalog)) {
          throw new Error('Live catalog returned an invalid payload.')
        }
        setProducts(catalog)
      })
      .catch((error: unknown) => {
        if (!active || (error as { name?: string })?.name === 'AbortError') return
        setCatalogError(
          error instanceof Error ? error.message : 'The live catalog is unavailable.',
        )
      })
      .finally(() => {
        if (active) setCatalogLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [personaId, catalogRevision])

  const featuredProduct = products[0] ?? null
  const gridProducts = selectStorefrontGridProducts(products, personaId)
  // Product rows and their order come from Aurora. This source-controlled
  // layer is only the editorial frame around each durable storefront edit.
  const edit = weekendEditForPersona(personaId)
  const editHeadline = splitHeadlineAtRe(edit.headline)
  const curatedHeadline =
    PERSONA_INTERESTS[personaId ?? 'fresh']?.curatedHeadline
    ?? 'Things worth discovering.'

  useEffect(() => {
    setChatSurface('drawer')
  }, [setChatSurface])

  useEffect(() => {
    document.body.classList.add('pellier-surface')
    return () => document.body.classList.remove('pellier-surface')
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.location.hash === '#shop') {
      requestAnimationFrame(() => {
        document.getElementById('shop')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
      })
    }
  }, [])

  const handleNavigate = (item: NavItem) => {
    if (item === 'account') {
      openModal('auth')
      return
    }
    if (item === 'home') {
      window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
      return
    }
    if (item === 'shop') {
      document.getElementById('shop')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
      return
    }
    if (item === 'ask-pellier') {
      // Open the concierge drawer — that's what "Ask Pellier" promises.
      openModal('drawer')
      return
    }
    const target = NAV_ROUTES[item]
    if (target) navigate(target)
  }

  const handleAddToBag = (product: PellierProduct) =>
    addToCart({
      productId: product.id,
      name: product.name,
      price: product.price,
      image: product.imageUrl,
      origin: 'manual',
    })

  const handleOpenCatalog = () => {
    document.getElementById('shop')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }

  const closeClientPreview = () => {
    const next = new URLSearchParams(searchParams)
    next.delete('clientPreview')
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="pellier-page-surface min-h-dvh bg-cream-50">
      <Header current="home" onNavigate={handleNavigate} />

      <main className="bg-cream">
        {clientPreviewId ? (
          <OperatorClientPreview
            customerId={clientPreviewId}
            onClose={closeClientPreview}
          />
        ) : null}

        {/* ── ACT 1: editorial statement, product photograph, concierge ── */}
        <PellierHero onBrowseCollection={handleOpenCatalog} />

        <section
          id="shop"
          className="w-full"
          aria-label="Featured products"
          style={{
            scrollMarginTop: 84,
            background: 'var(--cream-warm)',
            borderTop: '1px solid var(--rule-1)',
          }}
        >
          {catalogLoading ? (
            <div
              className="mx-auto max-w-[1440px] px-container-x py-24"
              role="status"
              aria-label="Loading live catalog"
            >
              <div className="h-[420px] animate-pulse rounded-[8px] border border-sand bg-cream" />
            </div>
          ) : null}

          {!catalogLoading && catalogError ? (
            <div className="mx-auto max-w-[760px] px-container-x py-24 text-center">
              <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-ink">
                Collection unavailable
              </p>
              <h2 className="mt-3 font-display text-espresso" style={{ fontSize: 'clamp(28px, 4vw, 44px)' }}>
                The collection is taking a moment.
              </h2>
              <p className="mt-4 font-sans text-[14px] text-ink-soft" role="alert">We couldn’t load the latest pieces. Please try again in a moment.</p>
              <button type="button" className="pellier-retry mt-5" onClick={() => setCatalogRevision(v => v + 1)}>Reload collection</button>
            </div>
          ) : null}

          {!catalogLoading && !catalogError && !featuredProduct ? (
            <div className="mx-auto max-w-[760px] px-container-x py-24 text-center">
              <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-ink">
                Live catalog empty
              </p>
              <p className="mt-4 font-sans text-[14px] text-ink-soft">
                Aurora has no current edit for this profile.
              </p>
            </div>
          ) : null}

          {!catalogLoading && !catalogError && featuredProduct ? (
            <>
              <div className="mx-auto w-full max-w-[1560px] px-container-x pb-12">
                <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
                  <Link
                    to={`/product/${featuredProduct.id}`}
                    aria-hidden="true"
                    tabIndex={-1}
                    className="relative block aspect-[4/5] overflow-hidden rounded-[var(--pellier-image-radius-lg)] shadow-warm-md"
                  >
                    <ResponsiveImage
                      src={featuredProduct.imageUrl}
                      alt={featuredProduct.name}
                      widths={[480, 960]}
                      sizes="(min-width: 1560px) 708px, (min-width: 1024px) 46vw, 100vw"
                      className="h-full w-full object-cover"
                      loading="lazy"
                      decoding="async"
                      pictureClassName="block h-full w-full"
                    />
                  </Link>

                  <div className="flex flex-col justify-center py-8 lg:py-0">
                    <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-ink">
                      {edit.eyebrow}
                    </p>
                    <h2
                      className="font-display text-espresso"
                      style={{
                        fontSize: 'clamp(36px, 5vw, 64px)',
                        lineHeight: 1.08,
                        fontWeight: 400,
                        whiteSpace: 'pre-line',
                      }}
                    >
                      {editHeadline.tail ? (
                        <>
                          <span>{editHeadline.lead}</span>
                          <span className="text-accent-ink">{editHeadline.tail}</span>
                        </>
                      ) : (
                        editHeadline.lead
                      )}
                    </h2>
                    <p className="mt-5 max-w-[440px] font-sans text-ink-soft" style={{ fontSize: 'clamp(14px, 1.1vw, 16px)', lineHeight: 1.65 }}>
                      {edit.subheadline}
                    </p>

                    <div className="mt-8 border-t border-sand/50 pt-6">
                      <p className="mb-1 font-sans text-[12px] text-ink-quiet">{featuredProduct.brand}</p>
                      <p className="font-display text-xl text-espresso">
                        <Link
                          to={`/product/${featuredProduct.id}`}
                          data-testid="featured-product-link"
                          className="inline-flex min-h-[44px] items-center transition-colors duration-fade hover:text-accent-ink"
                        >
                          {featuredProduct.name}
                        </Link>
                      </p>
                      <div className="mt-2 flex items-center gap-3 font-sans text-sm text-ink-soft">
                        <span className="font-medium text-espresso">${featuredProduct.price}</span>
                        <span>★ {featuredProduct.rating.toFixed(1)}</span>
                        <span className="text-ink-quiet">({featuredProduct.reviewCount})</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleAddToBag(featuredProduct)}
                        className="mt-5 min-h-12 cursor-pointer rounded-full bg-espresso px-8 py-3 font-sans text-sm font-medium text-cream-50 transition-colors duration-fade hover:bg-dusk"
                      >
                        Add to bag
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pellier-edit-shell pb-16 md:pb-24">
                <div className="mb-8">
                  <h2
                    data-testid="curated-headline"
                    className="font-display text-espresso"
                    style={{ fontSize: 'clamp(28px, 3.5vw, 44px)', lineHeight: 1.15, fontWeight: 400 }}
                  >
                    {curatedHeadline}
                  </h2>
                  <RationaleBand />
                </div>

                <div
                  key={`${prefsVersion}-${personaId ?? 'fresh'}`}
                  className="pellier-product-grid"
                >
                  {gridProducts.map((product, index) => (
                    <ProductCard
                      key={product.id}
                      product={product}
                      index={index % 3}
                      onAddToBag={handleAddToBag}
                      variant="editorial"
                    />
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </section>

        {/* The bridge into Labs. Sits after the shopping surfaces so the
            pellier makes its case before it offers the proof. */}
        <PellierApproach />

        <PellierServiceStrip />
      </main>

      <Footer />
      {/* CommandPill removed — hero search bar opens the drawer directly */}
      <PellierSpotlight />
    </div>
  )
}
