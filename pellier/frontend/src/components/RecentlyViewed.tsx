import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { getRecentlyViewed, clearRecentlyViewed } from '../utils/recentlyViewed'
import { useTheme } from '../App'

const RecentlyViewed = () => {
  const { theme } = useTheme()
  const [products, setProducts] = useState<any[]>([])

  useEffect(() => {
    const loadProducts = () => setProducts(getRecentlyViewed())
    loadProducts()
    const interval = setInterval(loadProducts, 2000)
    return () => clearInterval(interval)
  }, [])

  const handleClear = () => {
    clearRecentlyViewed()
    setProducts([])
  }

  if (products.length === 0) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 backdrop-blur-xl p-4 z-30" style={{ background: theme === 'dark' ? 'rgba(0, 0, 0, 0.95)' : 'rgba(255, 255, 255, 0.97)', borderTop: '1px solid var(--border-color)' }}>
      <div className="max-w-[1400px] mx-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-text-primary font-medium text-sm">Recently Viewed</h3>
          <button onClick={handleClear} className="text-text-secondary hover:text-text-primary text-xs flex items-center gap-1">
            <X className="h-3 w-3" /> Clear
          </button>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {products.map((product) => (
            <a
              key={product.id}
              href={`https://www.amazon.com/dp/${product.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 w-32 p-2 rounded-lg transition-all"
              style={{ background: theme === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)', border: '1px solid var(--border-color)' }}
            >
              <div className="w-full h-20 mb-2 rounded flex items-center justify-center" style={{ background: 'var(--input-bg)' }}>
                {product.image && (product.image.startsWith('http') || product.image.startsWith('data:')) ? (
                  <img src={product.image} alt={product.name} className="w-full h-full object-contain p-1" />
                ) : (
                  <span className="text-2xl">{product.image || ''}</span>
                )}
              </div>
              <p className="text-text-primary text-xs line-clamp-2 mb-1">{product.name}</p>
              <p className="text-text-secondary text-xs font-bold">${product.price.toFixed(2)}</p>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}

export default RecentlyViewed
