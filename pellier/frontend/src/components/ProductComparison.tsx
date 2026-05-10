/**
 * Product Comparison Mode — Side-by-side comparison table for products returned by agents.
 * Shows price, rating, reviews, stock with winner badges per attribute.
 */
import { X, Trophy, Star } from 'lucide-react'
import { type ChatProduct } from '../services/chat'

interface ProductComparisonProps {
  products: ChatProduct[]
  onClose: () => void
}

const ProductComparison = ({ products, onClose }: ProductComparisonProps) => {
  if (products.length < 2) return null

  const compareProducts = products.slice(0, 4)

  // Compute winners
  const lowestPrice = Math.min(...compareProducts.map(p => p.price))
  const highestRating = Math.max(...compareProducts.map(p => p.rating || 0))
  const mostReviews = Math.max(...compareProducts.map(p => p.reviews || 0))

  const getWinnerBadges = (product: ChatProduct) => {
    const badges: string[] = []
    if (product.price === lowestPrice) badges.push('Best Value')
    if ((product.rating || 0) === highestRating && highestRating > 0) badges.push('Best Rated')
    if ((product.reviews || 0) === mostReviews && mostReviews > 0) badges.push('Most Reviews')
    return badges
  }

  return (
    <div className="absolute inset-0 z-50 flex flex-col rounded-[20px] overflow-hidden animate-slideUp"
      style={{
        background: 'rgba(0, 0, 0, 0.95)',
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
        <div className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-semibold text-white">Compare Products</span>
          <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>({compareProducts.length} items)</span>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
          <X className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
        </button>
      </div>

      {/* Comparison Grid */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        <div className={`grid gap-3`} style={{ gridTemplateColumns: `repeat(${compareProducts.length}, minmax(0, 1fr))` }}>
          {compareProducts.map((product, idx) => {
            const badges = getWinnerBadges(product)
            const isImageUrl = product.image && (product.image.startsWith('http') || product.image.startsWith('data:'))

            return (
              <div key={idx} className="flex flex-col gap-2 p-3 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                {/* Winner badges */}
                {badges.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {badges.map((badge, i) => (
                      <span key={i} className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-semibold">
                        <Trophy className="h-2 w-2 inline mr-0.5" />{badge}
                      </span>
                    ))}
                  </div>
                )}

                {/* Image */}
                <div className="w-full h-16 rounded-lg flex items-center justify-center overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.06)' }}>
                  {isImageUrl ? (
                    <img src={product.image} alt={product.name} className="h-full object-contain p-1" />
                  ) : (
                    <span className="text-2xl">{product.image || ''}</span>
                  )}
                </div>

                {/* Name */}
                <div className="text-xs font-medium text-white line-clamp-2 min-h-[2rem]">
                  {product.name}
                </div>

                {/* Attributes */}
                <div className="space-y-1.5">
                  {/* Price */}
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-white/40">Price</span>
                    <span className={`text-sm font-bold ${product.price === lowestPrice ? 'text-green-400' : 'text-white/60'}`}>
                      ${product.price.toFixed(2)}
                    </span>
                  </div>

                  {/* Rating */}
                  {(product.rating || 0) > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-white/40">Rating</span>
                      <div className="flex items-center gap-1">
                        <Star className={`h-3 w-3 fill-current ${(product.rating || 0) === highestRating ? 'text-amber-400' : 'text-yellow-400'}`} />
                        <span className={`text-xs font-medium ${(product.rating || 0) === highestRating ? 'text-amber-400' : 'text-white/50'}`}>
                          {product.rating?.toFixed(1)}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Reviews */}
                  {(product.reviews || 0) > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-white/40">Reviews</span>
                      <span className={`text-xs ${(product.reviews || 0) === mostReviews ? 'text-blue-400 font-semibold' : 'text-white/50'}`}>
                        {product.reviews?.toLocaleString()}
                      </span>
                    </div>
                  )}

                  {/* Category */}
                  {product.category && (
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-white/40">Category</span>
                      <span className="text-[10px] text-white/60 truncate max-w-[80px]">{product.category}</span>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default ProductComparison
