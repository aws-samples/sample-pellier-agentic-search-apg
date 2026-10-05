import { apiFetch } from '../services/apiBase'
/**
 * PellierPage: the `/` route composition, products first.
 *
 *   Header (local storefront row, under the shared bar)
 *   → PellierHero: the statement, the large Ask Pellier bar and one row of
 *     suggestions
 *   → "This week at Pellier": the edit's pieces, one stock line per card,
 *     starting on the first screen
 *   → the approach band, the service strip and the footer
 *
 * Ask Pellier docks beside all of this as a 440px panel (ChatDrawer), open
 * by default on desktop; the shoppers are chosen there. A question from the
 * home bar or the dock puts the page into its results view (SearchResults):
 * the hero folds to its bar and the collection gives way to the pieces the
 * answer came from, until the shopper goes back to the whole store.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header, { type NavItem } from '../components/Header'
import PellierHero from '../components/PellierHero'
import PellierApproach from '../components/PellierApproach'
import PellierServiceStrip from '../components/PellierServiceStrip'
import ProductCard from '../components/ProductCard'
import Footer from '../components/Footer'
import PellierSpotlight from '../components/PellierSpotlight'
import SearchResults, { StoreFailedNotice } from '../components/SearchResults'
import { useStoreResults } from '../contexts/StoreResultsContext'
import { useAuth } from '../contexts/AuthContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { useCatalogStats } from '../hooks/useCatalogStats'
import { HOME_GRID } from '../copy'
import type { PellierProduct } from '../services/types'

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

export default function PellierPage() {
  const { prefsVersion } = useAuth()
  const { openModal, setChatSurface } = useUI()
  const { persona } = usePersona()
  const catalogStats = useCatalogStats()
  const navigate = useNavigate()
  const resultsView = useStoreResults()?.view
  const showingResults = resultsView?.kind === 'results'
  const resultsQuery = resultsView?.kind === 'results' ? resultsView.query : undefined


  const personaId = persona?.id ?? null
  // The persona names its own catalog grouping; signed out is the neutral edit.
  const storefrontEdit = persona?.edit ?? 'fresh'
  const [products, setProducts] = useState<PellierProduct[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogRevision, setCatalogRevision] = useState(0)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  // The home edit is a catalog grouping the persona names. Do not
  // retain a browser catalog when the active profile changes: a stale row is
  // worse than a visible unavailable state in a workshop about grounding.
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setCatalogLoading(true)
    setCatalogError(null)
    setProducts([])

    void apiFetch(`/api/products?persona=${encodeURIComponent(storefrontEdit)}`, {
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
  }, [storefrontEdit, catalogRevision])

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

  return (
    <div className="pellier-page-surface min-h-dvh bg-page">
      <Header current="home" onNavigate={handleNavigate} />

      <main className="bg-page">
        <PellierHero compact={showingResults} query={resultsQuery} />

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
            <StoreFailedNotice />
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

            {!catalogLoading && !catalogError && products.length === 0 ? (
              <div className="mx-auto max-w-[760px] px-container-x py-24 text-center">
                <p className="pellier-eyebrow">No pieces to show just now</p>
                <p className="mt-4 font-sans text-[14px] text-ink-2">
                  The collection returned no pieces for this edit. Choose another shopper or check back shortly.
                </p>
              </div>
            ) : null}

            {/* The edit's pieces from Aurora, in its order. The count says how
                many of the whole catalog this selection is. */}
            {!catalogLoading && !catalogError && products.length > 0 ? (
              <div className="pellier-edit-shell pellier-home-grid pb-16 md:pb-20">
                <div className="pellier-gridhead">
                  <h2 data-testid="home-grid-title" className="pellier-statement">
                    {HOME_GRID.TITLE}
                  </h2>
                  {catalogStats ? (
                    <span className="pellier-eyebrow" data-testid="home-grid-count">
                      {HOME_GRID.count(products.length, catalogStats.product_count)}
                    </span>
                  ) : null}
                </div>
                <div className="pellier-grid-frame">
                  <div
                    key={`${prefsVersion}-${personaId ?? 'fresh'}`}
                    className="pellier-product-grid"
                    data-testid="home-grid"
                  >
                    {products.map((product, index) => (
                      <ProductCard key={product.id} product={product} index={index % 3} />
                    ))}
                  </div>
                </div>
              </div>
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
