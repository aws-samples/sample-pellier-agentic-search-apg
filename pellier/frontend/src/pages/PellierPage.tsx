import { apiFetch } from '../services/apiBase'
/**
 * PellierPage: the `/` route composition, direction A.
 *
 *   Header (local storefront row, under the shared bar)
 *   → PellierHero: the statement, the large Ask Pellier bar and chips
 *   → the featured piece and its edit
 *   → the collection grid, one stock line per card
 *   → the approach band, the service strip and the footer
 *
 * Ask Pellier docks beside all of this as a 440px panel (ChatDrawer). A
 * question from the home bar or the dock puts the page into its results
 * view (SearchResults): the hero folds to its bar and the featured piece
 * and collection give way to the pieces the answer came from, until the
 * shopper goes back to the whole store.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header, { type NavItem } from '../components/Header'
import PellierHero from '../components/PellierHero'
import PellierApproach from '../components/PellierApproach'
import PellierServiceStrip from '../components/PellierServiceStrip'
import RationaleBand from '../components/RationaleBand'
import ProductCard from '../components/ProductCard'
import ResponsiveImage from '../components/ResponsiveImage'
import Footer from '../components/Footer'
import PellierSpotlight from '../components/PellierSpotlight'
import SearchResults from '../components/SearchResults'
import { useStoreResults } from '../contexts/StoreResultsContext'
import { useAuth } from '../contexts/AuthContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import {
  PERSONA_INTERESTS,
  storefrontEditFor,
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

export default function PellierPage() {
  const { prefsVersion } = useAuth()
  const { openModal, setChatSurface } = useUI()
  const { addToCart } = useCart()
  const { persona } = usePersona()
  const navigate = useNavigate()
  const showingResults = useStoreResults()?.view.kind === 'results'


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
    const profile = storefrontEditFor(personaId)
    setCatalogLoading(true)
    setCatalogError(null)
    setProducts([])

    void apiFetch(`/api/products?persona=${encodeURIComponent(profile)}`, {
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

  return (
    <div className="pellier-page-surface min-h-dvh bg-page">
      <Header current="home" onNavigate={handleNavigate} />

      <main className="bg-page">
        <PellierHero compact={showingResults} />

        {showingResults ? (
          <section
            id="shop"
            className="w-full"
            aria-label="Results"
            style={{
              scrollMarginTop: 'calc(var(--pellier-chrome-height, 64px) + var(--pellier-storefront-nav-height, 56px) + 16px)',
            }}
          >
            <SearchResults />
          </section>
        ) : null}

        {/* The store's catalog stays in state while results show, so it returns as it was. */}
        {showingResults ? null : (
          <section
            id="shop"
            className="w-full"
            aria-label="Featured products"
            style={{
              scrollMarginTop: 'calc(var(--pellier-chrome-height, 64px) + var(--pellier-storefront-nav-height, 56px) + 16px)',
            }}
          >
            {catalogLoading ? (
              <div
                className="pellier-edit-shell py-16"
                role="status"
                aria-label="Loading live catalog"
              >
                <div className="h-[420px] animate-pulse rounded-[16px] bg-recessed" />
              </div>
            ) : null}

            {!catalogLoading && catalogError ? (
              <div className="mx-auto max-w-[760px] px-container-x py-24 text-center">
                <p className="pellier-eyebrow">Collection unavailable</p>
                <h2 className="pellier-statement mt-3" style={{ fontSize: 'var(--text-section)' }}>
                  The collection is taking a moment.
                </h2>
                <p className="mt-4 font-sans text-[14px] text-ink-2" role="alert">We couldn’t load the latest pieces. Please try again in a moment.</p>
                <button type="button" className="pellier-retry mt-5" onClick={() => setCatalogRevision(v => v + 1)}>Reload collection</button>
              </div>
            ) : null}

            {!catalogLoading && !catalogError && !featuredProduct ? (
              <div className="mx-auto max-w-[760px] px-container-x py-24 text-center">
                <p className="pellier-eyebrow">No pieces to show just now</p>
                <p className="mt-4 font-sans text-[14px] text-ink-2">
                  The collection returned no pieces for this edit. Choose another shopper or check back shortly.
                </p>
              </div>
            ) : null}

            {!catalogLoading && !catalogError && featuredProduct ? (
              <>
                <div className="pellier-edit-shell pt-10 pb-12">
                  <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
                    <Link
                      to={`/product/${featuredProduct.id}`}
                      aria-hidden="true"
                      tabIndex={-1}
                      className="pellier-card-photo"
                    >
                      <ResponsiveImage
                        src={featuredProduct.imageUrl}
                        alt={featuredProduct.name}
                        widths={[480, 960, 1122]}
                        sizes="(min-width: 1560px) 708px, (min-width: 1024px) 46vw, 100vw"
                        className="h-full w-full object-cover"
                        loading="lazy"
                        decoding="async"
                        pictureClassName="block h-full w-full"
                      />
                    </Link>

                    <div className="flex flex-col justify-center py-4 lg:py-0">
                      <p className="pellier-eyebrow">{edit.eyebrow}</p>
                      <h2
                        className="pellier-statement mt-3"
                        style={{ fontSize: 'var(--text-section)', whiteSpace: 'pre-line' }}
                      >
                        {editHeadline.tail ? (
                          <>
                            <span>{editHeadline.lead}</span>
                            <span className="text-muted">{editHeadline.tail}</span>
                          </>
                        ) : (
                          editHeadline.lead
                        )}
                      </h2>
                      <p className="mt-4 max-w-[480px] font-sans text-[15px] leading-relaxed text-ink-2">
                        {edit.subheadline}
                      </p>

                      <div className="mt-7 border-t border-line pt-5">
                        <p className="pellier-card-brand">{featuredProduct.brand}</p>
                        <p className="mt-1 font-sans text-[17px] font-medium text-ink">
                          <Link
                            to={`/product/${featuredProduct.id}`}
                            data-testid="featured-product-link"
                            className="inline-flex min-h-[44px] items-center hover:underline underline-offset-4"
                          >
                            {featuredProduct.name}
                          </Link>
                        </p>
                        <p className="font-sans text-[15px] text-ink tabular-nums">${featuredProduct.price}</p>
                        <button
                          type="button"
                          onClick={() => handleAddToBag(featuredProduct)}
                          className="pellier-action mt-5"
                        >
                          Add to bag
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pellier-edit-shell pb-16 md:pb-20">
                  <div className="mb-6">
                    <div className="pellier-gridhead">
                      <h2 data-testid="curated-headline" className="pellier-statement">
                        {curatedHeadline}
                      </h2>
                    </div>
                    <RationaleBand />
                  </div>

                  <div
                    key={`${prefsVersion}-${personaId ?? 'fresh'}`}
                    className="pellier-product-grid"
                  >
                    {gridProducts.map((product, index) => (
                      <ProductCard key={product.id} product={product} index={index % 3} />
                    ))}
                  </div>
                </div>
              </>
            ) : null}
          </section>
        )}

        {/* The bridge into the labs. Sits after the shopping surfaces so the
            store makes its case before it offers the proof. */}
        <PellierApproach />

        <PellierServiceStrip />
      </main>

      <Footer />
      <PellierSpotlight />
    </div>
  )
}
