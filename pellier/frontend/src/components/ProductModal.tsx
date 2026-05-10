/**
 * Premium Product Modal Component - Apple-inspired Design
 * Full-screen modal with smooth animations and glassmorphism
 * DARK MODE READY
 */
import { X, Star, Package, TrendingUp, ExternalLink, ShoppingCart, Heart, Share2 } from 'lucide-react'
import { Product } from '../services/types'

interface ProductModalProps {
  product: Product
  onClose: () => void
}

const ProductModal = ({ product, onClose }: ProductModalProps) => {
  const {
    productId,
    product_description,
    imgurl,
    producturl,
    stars,
    reviews,
    price,
    category_name,
    isbestseller,
    boughtinlastmonth,
    quantity,
  } = product

  const formattedPrice = price ? `$${price.toFixed(2)}` : 'Price not available'

  const stockStatus =
    quantity === undefined || quantity === null
      ? 'Stock status unknown'
      : quantity === 0
      ? 'Out of Stock'
      : quantity < 10
      ? `Only ${quantity} left`
      : `${quantity} in stock`

  const stockColor =
    quantity === 0
      ? 'text-red-400 bg-red-500/10 border-red-500/20'
      : quantity !== undefined && quantity < 10
      ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
      : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden animate-in fade-in duration-300"
      aria-labelledby="modal-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="flex min-h-full items-center justify-center p-4 sm:p-8">
        <div
          className="relative rounded-[32px] shadow-2xl w-full max-w-5xl
                     overflow-hidden animate-in zoom-in-95 slide-in-from-bottom-8 duration-500"
          style={{
            maxHeight: 'calc(100vh - 64px)',
            background: 'var(--bg-primary)',
            backdropFilter: 'blur(40px)',
            WebkitBackdropFilter: 'blur(40px)',
            border: '1px solid var(--border-color)',
            boxShadow: '0 24px 60px rgba(0, 0, 0, 0.5)',
          }}
        >
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-6 right-6 z-10 p-3 rounded-full
                     backdrop-blur-xl shadow-lg hover:shadow-xl
                     transition-all duration-300 hover:scale-110 group"
            style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}
          >
            <X className="h-5 w-5 group-hover:text-white" style={{ color: 'var(--text-secondary)' }} strokeWidth={2} />
          </button>

          {/* Content Container */}
          <div className="overflow-y-auto custom-scrollbar" style={{ maxHeight: 'calc(100vh - 64px)' }}>
            <div className="grid md:grid-cols-2 gap-0">
              {/* Left: Image Section */}
              <div className="relative p-12
                            flex flex-col justify-center min-h-[500px]"
                   style={{ background: 'var(--input-bg)' }}>
                {/* Bestseller Badge */}
                {isbestseller && (
                  <div className="absolute top-8 left-8 px-4 py-2 rounded-full
                                bg-gradient-to-r from-amber-400 to-orange-500
                                shadow-lg">
                    <span className="text-sm font-bold text-white tracking-wide">
                      BESTSELLER
                    </span>
                  </div>
                )}

                {/* Product Image */}
                <div className="aspect-square rounded-3xl overflow-hidden shadow-lg"
                     style={{ background: 'var(--input-bg)' }}>
                  {imgurl ? (
                    <img
                      src={imgurl}
                      alt={product_description}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement
                        target.src = 'https://via.placeholder.com/600x600?text=No+Image'
                      }}
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <Package className="h-32 w-32" style={{ color: 'var(--text-tertiary)' }} strokeWidth={1.5} />
                    </div>
                  )}
                </div>

                {/* Stock Badge */}
                <div className={`mt-6 px-5 py-3 rounded-2xl font-semibold text-center border ${stockColor}`}>
                  {stockStatus}
                </div>
              </div>

              {/* Right: Details Section */}
              <div className="p-12 flex flex-col">
                {/* Product ID */}
                <div className="text-xs font-mono mb-4 tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                  SKU: {productId}
                </div>

                {/* Category */}
                {category_name && (
                  <div className="inline-block self-start px-4 py-2 mb-4
                                text-sm font-semibold rounded-full"
                       style={{ background: 'var(--input-bg)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)' }}>
                    {category_name}
                  </div>
                )}

                {/* Title */}
                <h2 className="text-3xl font-bold mb-6 leading-tight" style={{ color: 'var(--text-primary)' }}>
                  {product_description}
                </h2>

                {/* Rating */}
                {stars !== undefined && stars !== null && (
                  <div className="flex items-center gap-4 mb-6 pb-6"
                       style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <div className="flex items-center gap-1">
                      {[...Array(5)].map((_, i) => (
                        <Star
                          key={i}
                          className={`h-5 w-5 ${
                            i < Math.floor(stars)
                              ? 'text-amber-400 fill-amber-400'
                              : 'text-white/10 fill-white/10'
                          }`}
                          strokeWidth={0}
                        />
                      ))}
                    </div>
                    <span className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
                      {stars.toFixed(1)}
                    </span>
                    {reviews && (
                      <span className="font-medium" style={{ color: 'var(--text-tertiary)' }}>
                        ({reviews.toLocaleString()} reviews)
                      </span>
                    )}
                  </div>
                )}

                {/* Price */}
                <div className="mb-6">
                  <div className="text-5xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                    {formattedPrice}
                  </div>
                  {boughtinlastmonth && boughtinlastmonth > 0 && (
                    <div className="flex items-center gap-2" style={{ color: 'var(--text-tertiary)' }}>
                      <TrendingUp className="h-4 w-4" strokeWidth={2} />
                      <span className="text-sm font-medium">
                        {boughtinlastmonth.toLocaleString()} bought in the last month
                      </span>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3 mb-8">
                  <button
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-4
                             rounded-2xl font-semibold
                             shadow-lg hover:shadow-xl
                             transform transition-all duration-300 hover:scale-[1.02]"
                    style={{ background: 'var(--link-color)', color: '#ffffff' }}
                  >
                    <ShoppingCart className="h-5 w-5" strokeWidth={2} />
                    Add to Cart
                  </button>

                  <button
                    className="p-4 rounded-2xl font-semibold
                             transition-all duration-300 hover:scale-105 group hover:bg-white/10"
                    style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}
                  >
                    <Heart className="h-5 w-5 group-hover:text-red-400" style={{ color: 'var(--text-secondary)' }}
                           strokeWidth={2} />
                  </button>

                  <button
                    className="p-4 rounded-2xl font-semibold
                             transition-all duration-300 hover:scale-105 hover:bg-white/10"
                    style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}
                  >
                    <Share2 className="h-5 w-5" style={{ color: 'var(--text-secondary)' }} strokeWidth={2} />
                  </button>
                </div>

                {/* External Link */}
                {producturl && (
                  <a
                    href={producturl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 px-6 py-3
                             rounded-2xl font-medium hover:bg-white/10
                             transition-all duration-300 group"
                    style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}
                  >
                    <span>View on Amazon</span>
                    <ExternalLink className="h-4 w-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 
                                           transition-transform duration-300" strokeWidth={2} />
                  </a>
                )}

                {/* Product Information */}
                <div className="mt-auto pt-8" style={{ borderTop: '1px solid var(--border-color)' }}>
                  <h3 className="text-lg font-bold mb-4" style={{ color: 'var(--text-primary)' }}>
                    Product Information
                  </h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="mb-1" style={{ color: 'var(--text-tertiary)' }}>Product ID</div>
                      <div className="font-mono font-semibold text-white">
                        {productId}
                      </div>
                    </div>

                    {category_name && (
                      <div>
                        <div className="mb-1" style={{ color: 'var(--text-tertiary)' }}>Category</div>
                        <div className="font-semibold text-white">
                          {category_name}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="mb-1" style={{ color: 'var(--text-tertiary)' }}>Availability</div>
                      <div className={`font-semibold ${
                        quantity === 0
                          ? 'text-red-400'
                          : quantity !== undefined && quantity < 10
                          ? 'text-amber-400'
                          : 'text-emerald-400'
                      }`}>
                        {quantity !== undefined ? `${quantity} units` : 'Unknown'}
                      </div>
                    </div>

                    <div>
                      <div className="mb-1" style={{ color: 'var(--text-tertiary)' }}>Status</div>
                      <div className="font-semibold text-white">
                        {quantity === 0 ? 'Unavailable' : 'Available'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }

        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.15);
          border-radius: 4px;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.25);
        }
      `}</style>
    </div>
  )
}

export default ProductModal