/**
 * ProductArtifactCard — editorial product card for the storefront chat.
 *
 * Matches the `.artifact` element in docs/pellier-chat-experience.html.
 * Cream-elev background, 12px radius, "PULLED FOR YOU" eyebrow,
 * 160px image area, italic-serif name, espresso "Add to bag" pill,
 * outlined heart button. Mounts with artifact-mount keyframe (380ms).
 *
 * Used exclusively in PellierChat. The observatory branch continues
 * to use the dedicated storefront artifact treatment.
 */
import { useState } from 'react'
import { Heart } from 'lucide-react'
import type { ChatProduct } from '../services/chat'
import { imageSrc } from '../utils/assetPath'
import { productQuickActions } from '../utils/catalogFollowUps'
import StatusTag, { type TagTone } from './turn/StatusTag'
import '../styles/product-artifact.css'
import '../styles/turn.css'

interface ProductArtifactCardProps {
  product: ChatProduct
  onAddToCart?: () => void
  rankIndex?: number
  onPrompt?: (prompt: string) => void
}

interface CommerceSignal {
  label: string
  value: string
}

function confirmedAvailabilityLabel(quantity: number | null | undefined): string {
  if (typeof quantity !== 'number') return 'In stock'
  if (quantity <= 3) return `Only ${quantity} left`
  return 'In stock'
}

function availabilitySignal(product: ChatProduct): string {
  const availability = product.availability
  if (availability) {
    switch (availability.status) {
      case 'reconciled_in_stock':
        return confirmedAvailabilityLabel(availability.availableQuantity)
      case 'reconciled_out_of_stock':
        return 'Sold out'
      case 'observed_in_stock':
        return typeof availability.availableQuantity === 'number'
          ? `${availability.availableQuantity} observed`
          : 'Observed'
      case 'observed_out_of_stock':
        return 'No units observed'
      default:
        return 'Not verified'
    }
  }

  if (product.inStock === false || product.quantity === 0) return 'Sold out'
  if (typeof product.quantity === 'number') {
    if (product.quantity <= 3) return `Only ${product.quantity} left`
    return 'In stock'
  }
  if (product.inStock === true) return 'In stock'
  return 'Not verified'
}

/** Green for in stock, red for sold out, grey when stock was not read. */
export function stockTone(product: ChatProduct): TagTone {
  const status = product.availability?.status
  if (status === 'reconciled_in_stock' || status === 'observed_in_stock') return 'good'
  if (status === 'reconciled_out_of_stock' || status === 'observed_out_of_stock') return 'blocked'
  if (status) return 'pending'
  if (product.inStock === false || product.quantity === 0) return 'blocked'
  if (product.inStock === true || (typeof product.quantity === 'number' && product.quantity > 0)) return 'good'
  return 'pending'
}

function commerceSignals(product: ChatProduct): CommerceSignal[] {
  const signals: CommerceSignal[] = []
  if (product.category) {
    signals.push({ label: 'Category', value: product.category })
  }
  return signals
}

export default function ProductArtifactCard({
  product,
  onAddToCart,
  rankIndex = 0,
  onPrompt,
}: ProductArtifactCardProps) {
  const [saved, setSaved] = useState(false)
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

  const brand = product.category || 'Pellier'
  const rating = product.rating ?? product.reviews
  const isOwned = product.ownership === 'owned'

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

  const quickActions = productQuickActions(product)
  const signals = commerceSignals(product)

  return (
    <div className="pa-card">
      {/* Eyebrow */}
      <div className="pa-eyebrow">
        <span className="pa-eyebrow-left">
          <span className="pa-eyebrow-dot" />
          {isOwned ? 'Already in your collection' : 'Pulled for you'}
        </span>
        {!isOwned && (
          <span className={`pa-match pa-match-${matchLabel.toLowerCase().replace(' ', '-')}`}>
            {matchLabel}
          </span>
        )}
      </div>

      {/* Image area */}
      <div className="pa-image">
        {hasImage ? (
          <img
            src={imageSrc(product.image)}
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
        </div>
        {/* Stock lives here, in the labelled pill row, and only here: a second
            bare "8 left" in the meta line above read as a repeated claim. */}
        <div className="pa-commerce" aria-label="Shopping details">
          <StatusTag tone={stockTone(product)}>{availabilitySignal(product)}</StatusTag>
          {signals.map((signal) => (
            <span key={signal.label} className="pa-commerce-pill">
              <span>{signal.label}</span>
              <strong>{signal.value}</strong>
            </span>
          ))}
        </div>
        {!isOwned && onAddToCart && (
          <div className="pa-actions">
            <button
              type="button"
              className="pa-add"
              onClick={onAddToCart}
            >
              Add to bag
            </button>
            <button
              type="button"
              className={`pa-heart ${saved ? 'is-saved' : ''}`}
              aria-label={saved ? 'Saved' : 'Save'}
              aria-pressed={saved}
              onClick={() => setSaved((value) => !value)}
            >
              <Heart size={14} fill={saved ? 'currentColor' : 'none'} />
            </button>
          </div>
        )}
        {onPrompt && (
          <div className="pa-quick-actions">
            {quickActions.map(action => (
              <button
                key={action.label}
                type="button"
                className="pa-quick"
                onClick={() => onPrompt(action.prompt)}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
