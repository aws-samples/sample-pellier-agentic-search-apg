/**
 * ProductArtifactCard — editorial product card for the storefront chat.
 *
 * Matches the `.artifact` element in docs/pellier-chat-experience.html.
 * Cream-elev background, 12px radius, "PULLED FOR YOU" eyebrow,
 * 160px image area, italic-serif name, espresso "Add to bag" pill,
 * outlined heart button. Mounts with artifact-mount keyframe (380ms).
 *
 * Used exclusively in BoutiqueChat. The atelier branch continues
 * to use ProductCardConcierge.
 */
import { Heart } from 'lucide-react'
import type { ChatProduct } from '../services/chat'
import '../styles/product-artifact.css'

interface ProductArtifactCardProps {
  product: ChatProduct
  onAddToCart?: () => void
}

export default function ProductArtifactCard({
  product,
  onAddToCart,
}: ProductArtifactCardProps) {
  const hasImage =
    product.image &&
    (product.image.startsWith('http') || product.image.startsWith('data:') || product.image.startsWith('/'))

  const displayName = (() => {
    const name = product.name || ''
    const dashSplit = name.split(' — ')
    if (dashSplit.length > 1 && dashSplit[0].length <= 80) return dashSplit[0]
    return name.length <= 72
      ? name
      : name.substring(0, 72).replace(/\s+\S*$/, '') + '\u2026'
  })()

  const brand = product.category || 'Pellier Editions'
  const rating = product.rating ?? product.reviews
  const stockLabel =
    product.quantity != null && product.quantity > 0
      ? `${product.quantity} left`
      : product.inStock === false
        ? 'Out of stock'
        : null

  return (
    <div className="pa-card">
      {/* Eyebrow */}
      <div className="pa-eyebrow">
        <span className="pa-eyebrow-dot" />
        Pulled for you
      </div>

      {/* Image area */}
      <div className="pa-image">
        {hasImage ? (
          <img
            src={product.image}
            alt={displayName}
            className="pa-image-img"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
            }}
          />
        ) : null}
      </div>

      {/* Body */}
      <div className="pa-body">
        <div className="pa-brand">{brand}</div>
        <div className="pa-name">{displayName}</div>
        <div className="pa-meta">
          <span className="pa-price">
            ${product.price.toFixed(product.price % 1 === 0 ? 0 : 2)}
          </span>
          {rating != null && rating > 0 && (
            <span className="pa-rating">
              <span className="pa-star">&#9733;</span>
              {' '}{typeof product.rating === 'number' ? product.rating.toFixed(1) : rating}
              {product.reviews != null && (
                <span className="pa-reviews">({product.reviews})</span>
              )}
            </span>
          )}
          {stockLabel && (
            <span className="pa-stock">{stockLabel}</span>
          )}
        </div>
        <div className="pa-actions">
          <button
            type="button"
            className="pa-add"
            onClick={onAddToCart}
          >
            Add to bag
          </button>
          <button type="button" className="pa-heart" aria-label="Save">
            <Heart size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
