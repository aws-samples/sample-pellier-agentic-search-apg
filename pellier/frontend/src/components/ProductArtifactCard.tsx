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
  rankIndex?: number
  onPrompt?: (prompt: string) => void
}

export default function ProductArtifactCard({
  product,
  onAddToCart,
  rankIndex = 0,
  onPrompt,
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

  const matchLabel = (() => {
    const score = product.similarityScore
    if (typeof score === 'number' && Number.isFinite(score)) {
      if (score >= 0.86) return 'Top match'
      if (score >= 0.75) return 'Strong match'
      return 'Related'
    }
    if (rankIndex === 0) return 'Top match'
    if (rankIndex <= 2) return 'Strong match'
    return 'Related'
  })()

  const categorySignal = `${product.category ?? ''} ${product.name ?? ''}`.toLowerCase()
  const isApparelLike =
    /shirt|tee|dress|trouser|pants|pant|jacket|coat|overshirt|sweater|knit|wardrobe|wear/.test(
      categorySignal,
    )
  const swapLabel = isApparelLike ? 'Swap size/color' : 'Swap color'
  const productName = (product.name || 'this piece').trim()
  const swapPrompt = isApparelLike
    ? `Show ${productName} in another size or color.`
    : `Show ${productName} in another color.`
  const alternativesPrompt = `Show alternatives to ${productName} at a similar style and price.`
  const whyMatchPrompt = `Why is ${productName} a ${matchLabel.toLowerCase()} for this request?`

  return (
    <div className="pa-card">
      {/* Eyebrow */}
      <div className="pa-eyebrow">
        <span className="pa-eyebrow-left">
          <span className="pa-eyebrow-dot" />
          Pulled for you
        </span>
        <span className={`pa-match pa-match-${matchLabel.toLowerCase().replace(' ', '-')}`}>
          {matchLabel}
        </span>
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
        {onPrompt && (
          <div className="pa-quick-actions">
            <button
              type="button"
              className="pa-quick"
              onClick={() => onPrompt(swapPrompt)}
            >
              {swapLabel}
            </button>
            <button
              type="button"
              className="pa-quick"
              onClick={() => onPrompt(alternativesPrompt)}
            >
              Show alternatives
            </button>
            <button
              type="button"
              className="pa-quick"
              onClick={() => onPrompt(whyMatchPrompt)}
            >
              Why this match?
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
