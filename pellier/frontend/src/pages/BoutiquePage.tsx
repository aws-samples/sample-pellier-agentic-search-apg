/**
 * BoutiquePage — the `/` route composition (Boutique redesign).
 *
 * Two-act layout:
 *
 *   ACT 1 (above the fold — full viewport):
 *     Header (sticky) → BoutiqueHero (full-height search surface)
 *
 *   ACT 2 (below the fold — scroll to discover):
 *     Featured product image (weekender bag) + "Weekend, re:defined."
 *     → 8 remaining products in a staggered grid
 *     → "Because you asked..." editorial cards
 *     → Footer
 *
 * The hero occupies the entire viewport so the first impression is
 * the search bar. Scrolling reveals the editorial product showcase.
 */
import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import AnnouncementBar from '../components/AnnouncementBar'
import Header, { type NavItem } from '../components/Header'
import BoutiqueHero from '../components/BoutiqueHero'
import BoutiqueWelcomeBand from '../components/BoutiqueWelcomeBand'
import BecauseYouAsked from '../components/BecauseYouAsked'
import MemoryHandoffCard from '../components/MemoryHandoffCard'
import RationaleBand from '../components/RationaleBand'
import ProductCard from '../components/ProductCard'
import Footer from '../components/Footer'
// CommandPill removed — hero search bar is the primary entry point
import { useAuth } from '../contexts/AuthContext'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import {
  SHOWCASE_PRODUCTS,
  FRESH_PRODUCTS,
  MARCO_PRODUCTS,
  ANNA_PRODUCTS,
  THEO_PRODUCTS,
} from '../data/showcaseProducts'

const PERSONA_PRODUCTS: Record<string, typeof SHOWCASE_PRODUCTS> = {
  fresh: FRESH_PRODUCTS,
  marco: MARCO_PRODUCTS,
  anna: ANNA_PRODUCTS,
  theo: THEO_PRODUCTS,
}
import {
  PERSONA_INTERESTS,
  rankProductsForPersona,
  featuredProductIdForPersona,
  weekendEditForPersona,
} from '../data/personaCurations'
import { splitHeadlineAtRe } from '../utils/headlineAccent'

const NAV_ROUTES: Record<NavItem, string> = {
  home: '/',
  shop: '/#shop',
  storyboard: '/storyboard',
  stories: '/storyboard',
  discover: '/discover',
  about: '/about',
  account: '/',
  'ask-pellier': '/',
}

// Featured product + grid are now persona-aware (computed inside component)

export default function BoutiquePage() {
  const { prefsVersion } = useAuth()
  const { openModal, setChatSurface } = useUI()
  const { addToCart } = useCart()
  const { persona } = usePersona()
  const navigate = useNavigate()

  // Persona-aware featured product + grid ordering + weekend edit.
  const personaId = persona?.id ?? null

  // Each persona sees ONLY their 9 products — zero overlap
  const personaProducts = PERSONA_PRODUCTS[personaId ?? 'fresh'] ?? FRESH_PRODUCTS

  const featuredProduct = useMemo(() => {
    const fid = featuredProductIdForPersona(personaId)
    return personaProducts.find(p => p.id === fid) ?? personaProducts[0]
  }, [personaId, personaProducts])

  const gridProducts = useMemo(
    () => personaProducts.filter(p => p.id !== featuredProduct.id),
    [personaProducts, featuredProduct],
  )

  const weekendEdit = weekendEditForPersona(personaId)
  const weekendHeadlineParts = splitHeadlineAtRe(weekendEdit.headline)

  const rankedGridProducts = useMemo(
    () => rankProductsForPersona(gridProducts, personaId),
    [gridProducts, personaId],
  )
  const personaInterests = personaId ? PERSONA_INTERESTS[personaId] : undefined
  const isPersonalized =
    !!personaInterests &&
    Object.keys(personaInterests.tagWeights).length > 0
  const curatedEyebrow = personaInterests?.curatedEyebrow ?? 'Curated for you'
  const curatedHeadline =
    personaInterests?.curatedHeadline ?? 'Things worth discovering.'

  useEffect(() => {
    setChatSurface('drawer')
  }, [setChatSurface])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.location.hash === '#shop') {
      requestAnimationFrame(() => {
        document.getElementById('shop')?.scrollIntoView({ behavior: 'smooth' })
      })
    }
  }, [])

  const handleNavigate = (item: NavItem) => {
    if (item === 'account') {
      openModal('auth')
      return
    }
    if (item === 'home') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    if (item === 'shop') {
      document.getElementById('shop')?.scrollIntoView({ behavior: 'smooth' })
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

  const handleAddToBag = (product: typeof SHOWCASE_PRODUCTS[0]) =>
    addToCart({
      productId: product.id,
      name: product.name,
      price: product.price,
      image: product.imageUrl,
      origin: 'manual',
    })

  return (
    <div className="min-h-dvh bg-cream-50">
      {/* Announcement bar — full-width above the header */}
      <AnnouncementBar />

      <Header current="home" onNavigate={handleNavigate} />

      <main>
        {/* ── ACT 1: Full-viewport hero ── */}
        <BoutiqueHero />

        {/* ── Welcome band — dismissible, sits between the hero and the
             Weekend Edit. Symmetric with /atelier's AtelierWelcome so
             first-visit shoppers get a one-glance orientation without
             touching the photograph. ── */}
        <BoutiqueWelcomeBand />

        {/* ── Memory handoff card — the most demoable agentic moment on
             the homepage. For returning personas, surfaces what the
             agent remembers (saved item, holds in bag, restock watch)
             with each line tool-tagged. Fresh visitors get a
             learn-as-we-go variant in the same slot so the layout
             rhythm stays consistent. ── */}
        <MemoryHandoffCard />

        {/* ── ACT 2: Below the fold ── */}
        <section
          id="shop"
          className="w-full bg-cream-50"
          aria-label="Featured products"
          style={{ scrollMarginTop: 84 }}
        >
          {/* Featured product: large image + editorial title */}
          <div className="max-w-[1440px] mx-auto px-container-x pt-16 md:pt-24 pb-12">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">
              {/* Left: featured image */}
              <div className="relative aspect-[4/5] rounded-2xl overflow-hidden shadow-warm-md">
                <img
                  src={featuredProduct.imageUrl}
                  alt={featuredProduct.name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                {/* Subtle warm wash */}
                <div
                  className="absolute inset-0 pointer-events-none"
                  aria-hidden="true"
                  style={{
                    background: 'linear-gradient(180deg, rgba(247,243,238,0.05) 0%, rgba(59,47,47,0.12) 100%)',
                  }}
                />
              </div>

              {/* Right: editorial title + product info */}
              <div className="flex flex-col justify-center py-8 lg:py-0">
                <p className="text-[11px] font-sans font-semibold tracking-[0.22em] uppercase text-ink-quiet mb-4">
                  {weekendEdit.eyebrow}
                </p>
                <h2
                  className="font-display italic"
                  style={{
                    fontSize: 'clamp(36px, 5vw, 64px)',
                    lineHeight: 1.05,
                    letterSpacing: '-0.02em',
                    fontWeight: 400,
                    whiteSpace: 'pre-line',
                  }}
                >
                  {weekendHeadlineParts.tail ? (
                    <>
                      <span className="text-espresso">{weekendHeadlineParts.lead}</span>
                      <span className="text-accent-ink">{weekendHeadlineParts.tail}</span>
                    </>
                  ) : (
                    <span className="text-espresso">{weekendHeadlineParts.lead}</span>
                  )}
                </h2>
                <p
                  className="mt-5 max-w-[440px] font-sans text-ink-soft"
                  style={{
                    fontSize: 'clamp(14px, 1.1vw, 16px)',
                    lineHeight: 1.65,
                  }}
                >
                  {weekendEdit.subheadline}
                </p>

                {/* Featured product details */}
                <div className="mt-8 pt-6 border-t border-sand/50">
                  <p className="text-[10px] font-sans font-semibold tracking-[0.2em] uppercase text-ink-quiet mb-1">
                    {featuredProduct.brand}
                  </p>
                  <p className="font-display italic text-espresso text-xl">
                    {featuredProduct.name}
                  </p>
                  <div className="flex items-center gap-3 mt-2 text-sm text-ink-soft font-sans">
                    <span className="text-espresso font-medium">${featuredProduct.price}</span>
                    <span>★ {featuredProduct.rating.toFixed(1)}</span>
                    <span className="text-ink-quiet">({featuredProduct.reviewCount})</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleAddToBag(featuredProduct)}
                    className="mt-5 rounded-full bg-espresso text-cream-50 px-8 py-3 text-sm font-sans font-medium transition-colors duration-fade hover:bg-dusk cursor-pointer"
                  >
                    Add to bag
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Curated grid: 8 products, reordered by active persona.
              Fresh visitors get the canonical showcase sequence; Marco,
              Anna, and Theo see a tag-ranked ordering with a matching
              eyebrow + headline + "for <name>" chip so the
              personalization is visible rather than silent. */}
          <div className="max-w-[1440px] mx-auto px-container-x pb-16 md:pb-24">
            <div className="mb-8 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="relative flex h-2 w-2" aria-hidden="true">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
                  </span>
                  <p
                    data-testid="curated-eyebrow"
                    className="text-[11px] font-sans font-semibold tracking-[0.22em] uppercase text-ink-quiet"
                  >
                    {curatedEyebrow}
                  </p>
                </div>
                <h2
                  data-testid="curated-headline"
                  className="font-display italic text-espresso"
                  style={{
                    fontSize: 'clamp(28px, 3.5vw, 44px)',
                    lineHeight: 1.15,
                    letterSpacing: '-0.01em',
                    fontWeight: 400,
                  }}
                >
                  {curatedHeadline}
                </h2>
              </div>

              {/* Persona chip — renders only when a persona is active,
                  so the fresh anonymous view stays clean. */}
              {isPersonalized && persona && (
                <div
                  data-testid="curated-persona-chip"
                  className="inline-flex items-center gap-2 self-start md:self-end"
                  style={{
                    fontFamily: 'var(--sans)',
                    fontSize: '11px',
                    letterSpacing: '0.14em',
                    textTransform: 'uppercase',
                    fontWeight: 500,
                    color: '#1f1410',
                    padding: '6px 12px',
                    borderRadius: 999,
                    background: 'var(--cream-warm)',
                    border: '1px solid rgba(31,20,16,0.12)',
                  }}
                >
                  <span aria-hidden style={{ color: '#a8423a', fontSize: '7px' }}>
                    &#9679;
                  </span>
                  <span>For {persona.display_name.split(' ')[0]}</span>
                </div>
              )}
            </div>

            {/* Rationale band — italic pull-quote restating the user's
                ask and the agent's curation strategy. Renders directly
                above the grid so the products that follow read as the
                answer to a stated rationale, not a generic merchandise
                row. Per-product "because" lines on each card carry the
                reasoning down to the item level. */}
            <RationaleBand />

            <div
              // Re-mount on prefsVersion OR persona change so the grid's
              // per-card reveal animation re-fires for the new ordering.
              key={`${prefsVersion}-${personaId ?? 'fresh'}`}
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '1.5rem',
              }}
            >
              {rankedGridProducts.map((product, index) => (
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

        {/* "Because you asked..." editorial cards */}
        <BecauseYouAsked />
      </main>

      <Footer />
      {/* CommandPill removed — hero search bar opens the drawer directly */}
    </div>
  )
}
