/**
 * PellierPage: the `/` route composition, products first.
 *
 *   Header (local storefront row, under the shared bar)
 *   → PellierHero: the statement, the large Ask Pellier bar and one row of
 *     suggestions
 *   → HomeGrid: "This week at Pellier" (or the shopper's edit), one stock
 *     line per card, starting on the first screen, then the rest of the
 *     catalog twelve pieces a page
 *   → the approach band, the service strip and the footer
 *
 * Ask Pellier docks beside all of this as a 440px panel (ChatDrawer), open
 * by default on desktop; the shoppers are chosen there. A question from the
 * home bar or the dock puts the page into its results view (SearchResults):
 * the hero folds to its bar and the collection gives way to the pieces the
 * answer came from, until the shopper goes back to the whole store.
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Header, { type NavItem } from '../components/Header'
import PellierHero from '../components/PellierHero'
import PellierApproach from '../components/PellierApproach'
import PellierServiceStrip from '../components/PellierServiceStrip'
import HomeGrid from '../components/HomeGrid'
import Footer from '../components/Footer'
import PellierSpotlight from '../components/PellierSpotlight'
import SearchResults, { StoreFailedNotice } from '../components/SearchResults'
import { useStoreResults } from '../contexts/StoreResultsContext'
import { useUI } from '../contexts/UIContext'

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
  const { openModal, setChatSurface } = useUI()
  const navigate = useNavigate()
  const resultsView = useStoreResults()?.view
  const showingResults = resultsView?.kind === 'results'
  const resultsQuery = resultsView?.kind === 'results' ? resultsView.query : undefined

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

        {/* The store stays mounted, hidden, while results show, so it returns
            as it was: the same page of the catalog, with no second read. */}
        <section
          id={showingResults ? undefined : 'shop'}
          hidden={showingResults}
          className="w-full"
          aria-label="Featured products"
          style={{
            scrollMarginTop: 'calc(var(--pellier-chrome-height, 64px) + var(--pellier-storefront-nav-height, 56px) + 16px)',
          }}
        >
          <StoreFailedNotice />
          {/* Twelve pieces a page, through the whole catalog: page 1 is the
              edit, the later pages the rest, in Aurora's order. */}
          <HomeGrid />
        </section>

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
