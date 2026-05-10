/**
 * ProductGrid — the 9-card editorial grid on the home page.
 *
 * Validates Requirements 1.6.1, 1.6.3, 1.6.6, 4.2, 16.3.
 *
 * Layout (Req 16.3 — fluid responsive):
 *   - CSS Grid with `auto-fill` and `minmax(280px, 1fr)` so columns
 *     adjust dynamically based on available width:
 *     - Mobile  (<768px):   1 column
 *     - 14" laptops (~1280px): 2-3 columns
 *     - 16" displays (~1440px+): 3-4 columns
 *   - `gap-6` for card spacing
 *   - Fluid container: `max-w-[1440px] mx-auto px-container-x`
 *
 * Parallax re-firing on preference save (Req 1.6.6):
 *   - The grid is expected to be mounted by its parent with
 *     `<ProductGrid key={prefsVersion} ... />`. When `prefsVersion`
 *     advances (after `useAuth().savePreferences(...)`), React tears
 *     down this tree and mounts a fresh one. Every `<ProductCard/>`
 *     attaches a new observer, so parallax fires again for the
 *     now-re-ordered list.
 *
 * Data (Req 1.6.3):
 *   - `products` prop defaults to the 9 showcase products from
 *     `storefront.md` so the grid renders without a running backend.
 *
 * Stagger:
 *   - Each card receives its column position within its row (`index % 3`)
 *     as the stagger index, which the card's observer converts into a
 *     `220ms * (index % 3)` delay. This produces the left-to-right sweep
 *     per row documented in `storefront.md`.
 *
 * Phase 2 redesign: replaced fixed breakpoint grid with CSS Grid auto-fill
 * for fluid column adjustment. Uses new design tokens for container and
 * background.
 */
import type { BoutiqueProduct } from '../services/types'
import { SHOWCASE_PRODUCTS } from '../data/showcaseProducts'
import ProductCard from './ProductCard'

interface ProductGridProps {
  /**
   * Products to render. Defaults to the 9 showcase products from
   * `storefront.md`. When the personalized endpoint lands, the parent
   * passes in the server-sorted list instead.
   */
  products?: BoutiqueProduct[]
  /** Called when a card's `Add to bag` button is clicked. */
  onAddToBag?: (product: BoutiqueProduct) => void
}

export default function ProductGrid({
  products = SHOWCASE_PRODUCTS,
  onAddToBag,
}: ProductGridProps) {
  return (
    <section
      id="shop"
      data-testid="product-grid"
      aria-label="Featured products"
      className="w-full bg-cream-50 py-8 pb-12"
      style={{
        scrollMarginTop: 84, // clear the sticky header when scrolled to
      }}
    >
      <div
        className="max-w-[1440px] mx-auto px-container-x"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '1.5rem',
        }}
      >
        {products.map((product, index) => (
          <ProductCard
            key={product.id}
            product={product}
            index={index % 3}
            onAddToBag={onAddToBag}
          />
        ))}
      </div>
    </section>
  )
}
