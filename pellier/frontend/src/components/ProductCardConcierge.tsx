/**
 * ProductCardConcierge — slim editorial product card used inside
 * ConciergeModal. Matches the cream/ink boutique palette of the rest
 * of the modal (ProductCardCompact is dark-themed for the workshop /
 * RAG surfaces and stays).
 *
 * Layout: small square image on the left, brand eyebrow + title + price
 * stacked on the right. Optional "Why recommended" popover is preserved
 * but muted to fit the editorial feel.
 */
import { useState } from 'react'
import { Lightbulb, ShoppingCart } from 'lucide-react'
import { addRecentlyViewed } from '../utils/recentlyViewed'
import { type AgentType } from '../utils/agentIdentity'

interface Product {
  id: number
  name: string
  price: number
  rating?: number
  stars?: number
  reviews?: number
  image?: string
  category?: string
  url?: string
  quantity?: number
  similarityScore?: number
  originalPrice?: number
  discountPercent?: number
  inStock?: boolean
}

interface ProductCardConciergeProps {
  product: Product
  onAddToCart?: () => void
  agentSource?: AgentType
  recommendationReasons?: string[]
}

const CREAM = '#fbf4e8'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'

const ProductCardConcierge = ({
  product,
  onAddToCart,
  recommendationReasons,
}: ProductCardConciergeProps) => {
  const [showReasons, setShowReasons] = useState(false)
  const href = product.url || ''
  const isImageUrl =
    product.image &&
    (product.image.startsWith('http') || product.image.startsWith('data:'))

  const displayName = (() => {
    const name = product.name || ''
    const dashSplit = name.split(' — ')
    if (dashSplit.length > 1 && dashSplit[0].length <= 80) return dashSplit[0]
    if (name.length <= 64) return name
    return name.substring(0, 64).replace(/\s+\S*$/, '') + '…'
  })()

  const eyebrow = product.category || 'Pellier Editions'

  return (
    <div
      className="flex gap-3.5 p-3 rounded-2xl transition-colors"
      style={{
        background: '#ffffff',
        border: '1px solid rgba(45, 24, 16, 0.08)',
      }}
    >
      <a
        href={href || undefined}
        target={href ? '_blank' : undefined}
        rel="noopener noreferrer"
        onClick={() =>
          addRecentlyViewed({
            id: product.id,
            name: product.name,
            price: product.price,
            image: product.image,
          })
        }
        className="w-[72px] h-[72px] rounded-xl flex-shrink-0 overflow-hidden flex items-center justify-center"
        style={{ background: CREAM }}
      >
        {isImageUrl ? (
          <img
            src={product.image}
            alt={displayName}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
              const parent = e.currentTarget.parentElement
              if (parent && !parent.querySelector('.img-fallback')) {
                const span = document.createElement('span')
                span.className = 'img-fallback text-xl'
                span.style.opacity = '0.4'
                span.textContent = '\uD83D\uDCE6'
                parent.appendChild(span)
              }
            }}
          />
        ) : (
          <span className="text-2xl" style={{ opacity: 0.5 }}>
            {product.image || '\uD83D\uDCE6'}
          </span>
        )}
      </a>

      <div className="flex-1 min-w-0 flex flex-col justify-center gap-1">
        <div
          className="text-[10px] uppercase tracking-[1.4px] font-medium"
          style={{ color: INK_QUIET }}
        >
          {eyebrow}
        </div>
        <a
          href={href || undefined}
          target={href ? '_blank' : undefined}
          rel="noopener noreferrer"
          className="block"
        >
          <h4
            className="text-[14.5px] leading-tight font-semibold line-clamp-2"
            style={{ color: INK, fontFamily: "'Fraunces', serif" }}
          >
            {displayName}
          </h4>
        </a>
        <div className="flex items-center justify-between mt-0.5">
          <span
            className="text-[14px] font-semibold tracking-tight"
            style={{ color: INK }}
          >
            ${product.price.toFixed(product.price % 1 === 0 ? 0 : 2)}
          </span>
          {onAddToCart && (
            <button
              type="button"
              onClick={onAddToCart}
              aria-label="Add to cart"
              className="p-1.5 rounded-full transition-opacity hover:opacity-80"
              style={{ color: INK_SOFT }}
            >
              <ShoppingCart className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {recommendationReasons && recommendationReasons.length > 0 && (
          <div className="relative mt-0.5">
            <button
              onClick={(e) => {
                e.stopPropagation()
                setShowReasons(!showReasons)
              }}
              className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md"
              style={{ color: INK_SOFT }}
            >
              <Lightbulb className="h-3 w-3" />
              Why recommended
            </button>
            {showReasons && (
              <div
                className="absolute left-0 top-full mt-1 z-20 p-2.5 rounded-lg text-[11px] space-y-1 min-w-[200px]"
                style={{
                  background: CREAM,
                  border: '1px solid rgba(45, 24, 16, 0.08)',
                  color: INK_SOFT,
                }}
              >
                {recommendationReasons.map((reason, i) => (
                  <div key={i} className="flex items-start gap-1.5">
                    <span style={{ color: INK_QUIET }}>•</span>
                    {reason}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ProductCardConcierge
