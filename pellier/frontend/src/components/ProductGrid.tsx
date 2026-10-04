/**
 * ProductGrid: the collection as a three-across grid of ProductCards.
 *
 * Callers supply product rows read from Aurora. This presentational
 * component never substitutes a browser fixture for a live catalog.
 *
 * Each card receives its column position within its row (`index % 3`) as
 * the stagger index, which the card's observer converts into a short delay,
 * so a row reveals left to right. A parent that remounts the grid with a new
 * `key` (for example on a preference save) re-fires the reveal.
 */
import type { PellierProduct } from '../services/types'
import ProductCard from './ProductCard'

interface ProductGridProps {
  /** Products returned by the live catalog endpoint. */
  products: PellierProduct[]
}

export default function ProductGrid({ products }: ProductGridProps) {
  return (
    <section
      id="shop"
      data-testid="product-grid"
      aria-label="Featured products"
      className="pellier-edit-shell py-8 pb-12"
      style={{
        scrollMarginTop: 'calc(var(--pellier-chrome-height, 64px) + 20px)',
      }}
    >
      <div className="pellier-product-grid">
        {products.map((product, index) => (
          <ProductCard key={product.id} product={product} index={index % 3} />
        ))}
      </div>
    </section>
  )
}
