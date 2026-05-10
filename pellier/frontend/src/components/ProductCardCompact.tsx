import { useState } from 'react'
import { ShoppingCart, Star, ExternalLink, Lightbulb } from 'lucide-react'
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

interface ProductCardCompactProps {
  product: Product
  onAddToCart?: () => void
  agentSource?: AgentType
  similarityScore?: number
  recommendationReasons?: string[]
}

const renderStars = (rating: number) => {
  const fullStars = Math.floor(rating)
  const hasHalf = rating - fullStars >= 0.25
  const stars = []
  for (let i = 0; i < 5; i++) {
    if (i < fullStars) {
      stars.push(<Star key={i} className="h-3 w-3 fill-amber-400 text-amber-400" />)
    } else if (i === fullStars && hasHalf) {
      stars.push(
        <span key={i} className="relative inline-flex h-3 w-3">
          <Star className="h-3 w-3 text-amber-400/30 absolute" />
          <span className="overflow-hidden w-[50%] absolute">
            <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
          </span>
        </span>
      )
    } else {
      stars.push(<Star key={i} className="h-3 w-3 text-amber-400/30" />)
    }
  }
  return stars
}

const ProductCardCompact = ({ product, onAddToCart, similarityScore, recommendationReasons }: ProductCardCompactProps) => {
  const [showReasons, setShowReasons] = useState(false)
  // Construct Amazon URL from product ID if url is missing
  const amazonUrl = product.url || ''

  // Check if image is a valid URL or emoji
  const isImageUrl = product.image && (product.image.startsWith('http') || product.image.startsWith('data:'))
  const displayRating = product.rating || product.stars
  const score = similarityScore || product.similarityScore

  // Truncate long product descriptions to a short name
  const displayName = (() => {
    const name = product.name || ''
    const dashSplit = name.split(' — ')
    if (dashSplit.length > 1 && dashSplit[0].length <= 80) return dashSplit[0]
    if (name.length <= 60) return name
    return name.substring(0, 60).replace(/\s+\S*$/, '') + '...'
  })()

  return (
    <div
      className="relative flex gap-3.5 p-3.5 rounded-xl transition-all duration-300 group hover:scale-[1.015] hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)] hover:border-white/15"
      style={{
        background: 'var(--input-bg)',
        border: '1px solid var(--border-color)',
      }}
    >
      {/* Product Image */}
      <a
        href={amazonUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => addRecentlyViewed({ id: product.id, name: product.name, price: product.price, image: product.image })}
        className="w-[88px] h-[88px] rounded-xl flex-shrink-0 overflow-hidden transition-all flex items-center justify-center"
        style={{ background: 'rgba(255,255,255,0.09)' }}
      >
        {isImageUrl ? (
          <img
            src={product.image}
            alt={displayName}
            className="w-full h-full object-contain p-2 transition-transform duration-500 group-hover:scale-110"
            onError={(e) => {
              e.currentTarget.style.display = 'none'
              const parent = e.currentTarget.parentElement
              if (parent && !parent.querySelector('.img-fallback')) {
                const span = document.createElement('span')
                span.className = 'img-fallback text-2xl opacity-40'
                span.textContent = '\uD83D\uDCE6'
                parent.appendChild(span)
              }
            }}
          />
        ) : (
          <span className="text-3xl">{product.image || '\uD83D\uDCE6'}</span>
        )}
      </a>

      {/* Product Info */}
      <div className="flex-1 min-w-0 flex flex-col justify-between">
        <div>
          <a
            href={amazonUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block group/link"
          >
            <h4 className="text-text-primary font-medium text-[13.5px] mb-1 line-clamp-2 leading-snug transition-colors group-hover/link:underline">
              {displayName}
            </h4>
          </a>
          <div className="flex items-center gap-2 text-xs flex-wrap mt-0.5">
            {product.category && (
              <span
                className="px-2 py-0.5 rounded-md text-[10px] font-medium text-text-secondary"
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                {product.category}
              </span>
            )}
            {displayRating && (
              <div className="flex items-center gap-1">
                <div className="flex items-center gap-px">
                  {renderStars(displayRating)}
                </div>
                <span className="text-text-secondary text-[11px] font-medium">{displayRating.toFixed(1)}</span>
              </div>
            )}
            {product.reviews && (
              <span className="text-text-secondary opacity-60 text-[11px]">({product.reviews.toLocaleString()})</span>
            )}
          </div>

          {/* Why recommended tooltip */}
          {recommendationReasons && recommendationReasons.length > 0 && (
            <div className="mt-1.5 relative">
              <button
                onClick={(e) => { e.stopPropagation(); setShowReasons(!showReasons) }}
                className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md transition-colors hover:bg-white/10"
                style={{ color: 'rgba(251, 191, 36, 0.8)' }}
              >
                <Lightbulb className="h-3 w-3" />
                Why recommended
              </button>
              {showReasons && (
                <div
                  className="absolute left-0 top-full mt-1 z-20 p-2.5 rounded-lg text-[11px] space-y-1 min-w-[200px]"
                  style={{
                    background: 'rgba(0, 0, 0, 0.92)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    backdropFilter: 'blur(20px)',
                  }}
                >
                  {recommendationReasons.map((reason, i) => (
                    <div key={i} className="flex items-start gap-1.5" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                      <span style={{ color: 'rgba(251, 191, 36, 0.6)' }}>•</span>
                      {reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            {product.originalPrice && product.originalPrice > product.price ? (
              <>
                <span className="text-text-secondary text-[13px] line-through opacity-60">${product.originalPrice.toFixed(2)}</span>
                <span className="font-bold text-base tracking-tight text-green-400">${product.price.toFixed(2)}</span>
                {product.discountPercent && product.discountPercent > 0 && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md" style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80' }}>
                    -{product.discountPercent}%
                  </span>
                )}
              </>
            ) : (
              <span className="font-bold text-base tracking-tight" style={{ color: 'var(--link-color)' }}>${product.price.toFixed(2)}</span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {/* View link */}
            <a
              href={amazonUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-60 hover:!opacity-100"
            >
              <ExternalLink className="h-3.5 w-3.5 text-text-secondary" />
            </a>
            {onAddToCart && (
              <button
                onClick={onAddToCart}
                className="p-2 rounded-lg transition-all duration-300 hover:scale-110 active:scale-95"
                style={{ background: 'var(--link-color)' }}
              >
                <ShoppingCart className="h-4 w-4 text-white" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Stock badge - overlaid */}
      {product.quantity !== undefined && (
        <span
          className="absolute top-2 right-2 px-2 py-0.5 rounded-full text-[9px] font-semibold"
          style={{
            background: product.quantity === 0 ? 'rgba(239, 68, 68, 0.2)' : product.quantity < 10 ? 'rgba(251, 191, 36, 0.2)' : 'rgba(34, 197, 94, 0.15)',
            color: product.quantity === 0 ? '#ef4444' : product.quantity < 10 ? '#fbbf24' : '#22c55e',
            border: `1px solid ${product.quantity === 0 ? 'rgba(239, 68, 68, 0.4)' : product.quantity < 10 ? 'rgba(251, 191, 36, 0.4)' : 'rgba(34, 197, 94, 0.3)'}`,
            backdropFilter: 'blur(8px)',
          }}
        >
          {product.quantity === 0 ? 'Out of Stock' : product.quantity < 10 ? `${product.quantity} left` : 'In Stock'}
        </span>
      )}

      {/* Similarity score bar (bottom) */}
      {score && score > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-[2px] rounded-b-xl overflow-hidden">
          <div
            className="h-full rounded-b-xl"
            style={{
              width: `${Math.min(score * 100, 100)}%`,
              background: 'linear-gradient(90deg, var(--link-color), #3b82f6)',
              opacity: 0.5,
            }}
          />
        </div>
      )}
    </div>
  )
}

export default ProductCardCompact
