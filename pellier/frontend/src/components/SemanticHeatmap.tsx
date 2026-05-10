/**
 * Semantic Search Heatmap — Visual scatter layout where position represents semantic similarity.
 * Products cluster by similarity with category labels and color-coded relevance.
 */
import { useState } from 'react'
import { X, Star } from 'lucide-react'

interface HeatmapProduct {
  productId: number
  product_description: string
  price: number
  stars?: number
  reviews?: number
  category_name?: string
  imgurl?: string
  similarity_score?: number
}

interface SemanticHeatmapProps {
  results: HeatmapProduct[]
  onClose: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  'headphone': '#3b82f6',
  'laptop': '#10b981',
  'camera': '#f59e0b',
  'gaming': '#ef4444',
  'smart home': '#8b5cf6',
  'cable': '#06b6d4',
  'default': '#a855f7',
}

function getCategoryColor(category?: string): string {
  if (!category) return CATEGORY_COLORS.default
  const lower = category.toLowerCase()
  for (const [key, color] of Object.entries(CATEGORY_COLORS)) {
    if (lower.includes(key)) return color
  }
  return CATEGORY_COLORS.default
}

const SemanticHeatmap = ({ results, onClose }: SemanticHeatmapProps) => {
  const [hoveredId, setHoveredId] = useState<number | null>(null)

  if (results.length === 0) return null

  const WIDTH = 600
  const HEIGHT = 400
  const CENTER_X = WIDTH / 2
  const CENTER_Y = HEIGHT / 2
  const MAX_RADIUS = 180

  // Group by category for cluster labels
  const categories = new Map<string, { count: number; avgAngle: number }>()

  const getPosition = (similarity: number, index: number, total: number) => {
    const angle = (index / total) * 2 * Math.PI - Math.PI / 2
    const normalizedSim = Math.max(similarity || 0.5, 0.3)
    const radius = (1 - normalizedSim) * MAX_RADIUS
    return {
      x: CENTER_X + radius * Math.cos(angle),
      y: CENTER_Y + radius * Math.sin(angle),
      angle,
    }
  }

  // Compute positions
  const positioned = results.map((product, index) => {
    const pos = getPosition(product.similarity_score || 0.5, index, results.length)
    const cat = product.category_name || 'Other'
    const existing = categories.get(cat)
    if (existing) {
      existing.count++
      existing.avgAngle = (existing.avgAngle + pos.angle) / 2
    } else {
      categories.set(cat, { count: 1, avgAngle: pos.angle })
    }
    return { ...product, ...pos }
  })

  return (
    <div className="relative w-full h-full">
      {/* Close button */}
      <button onClick={onClose} className="absolute top-2 right-2 z-10 p-1.5 rounded-lg hover:bg-white/10 transition-colors">
        <X className="h-4 w-4 text-gray-400" />
      </button>

      <div className="text-center mb-2">
        <span className="text-[10px] text-gray-500">Center = highest relevance · Edge = lower relevance</span>
      </div>

      {/* Heatmap container */}
      <div className="relative mx-auto" style={{ width: WIDTH, height: HEIGHT }}>
        {/* Background rings */}
        {[0.33, 0.66, 1].map((scale, i) => (
          <div
            key={i}
            className="absolute rounded-full border border-purple-500/10"
            style={{
              width: MAX_RADIUS * 2 * scale,
              height: MAX_RADIUS * 2 * scale,
              left: CENTER_X - MAX_RADIUS * scale,
              top: CENTER_Y - MAX_RADIUS * scale,
            }}
          />
        ))}

        {/* Center glow */}
        <div
          className="absolute rounded-full"
          style={{
            width: 40, height: 40,
            left: CENTER_X - 20, top: CENTER_Y - 20,
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.3) 0%, transparent 70%)',
          }}
        />

        {/* Product bubbles */}
        {positioned.map((product) => {
          const sim = product.similarity_score || 0.5
          const size = Math.max(24, (product.stars || 3) * 8)
          const color = getCategoryColor(product.category_name)
          const isHovered = hoveredId === product.productId

          return (
            <div
              key={product.productId}
              className="absolute transition-all duration-300 cursor-pointer"
              style={{
                left: product.x - size / 2,
                top: product.y - size / 2,
                width: size,
                height: size,
                zIndex: isHovered ? 50 : 1,
              }}
              onMouseEnter={() => setHoveredId(product.productId)}
              onMouseLeave={() => setHoveredId(null)}
            >
              {/* Bubble */}
              <div
                className="w-full h-full rounded-full border-2 flex items-center justify-center transition-all duration-200"
                style={{
                  background: `${color}${Math.round(sim * 60 + 20).toString(16).padStart(2, '0')}`,
                  borderColor: isHovered ? color : `${color}60`,
                  transform: isHovered ? 'scale(1.5)' : 'scale(1)',
                  boxShadow: isHovered ? `0 0 20px ${color}40` : undefined,
                }}
              >
                {product.stars && <Star className="h-2 w-2 text-white/80 fill-current" />}
              </div>

              {/* Hover tooltip */}
              {isHovered && (
                <div
                  className="absolute z-50 p-2.5 rounded-lg whitespace-nowrap animate-slideUp"
                  style={{
                    bottom: size + 8,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    background: 'rgba(13, 13, 26, 0.95)',
                    border: `1px solid ${color}60`,
                    backdropFilter: 'blur(10px)',
                    minWidth: 180,
                  }}
                >
                  <div className="text-xs font-medium text-white line-clamp-2 mb-1">
                    {product.product_description?.substring(0, 60)}...
                  </div>
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-purple-300 font-bold">${product.price?.toFixed(2)}</span>
                    {product.stars && (
                      <span className="text-yellow-400 flex items-center gap-0.5">
                        <Star className="h-2 w-2 fill-current" />{product.stars.toFixed(1)}
                      </span>
                    )}
                    <span className="text-gray-400">Sim: {(sim * 100).toFixed(0)}%</span>
                  </div>
                  {product.category_name && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full mt-1 inline-block" style={{ background: `${color}30`, color }}>
                      {product.category_name}
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* Category cluster labels */}
        {Array.from(categories.entries()).map(([cat, data]) => {
          if (data.count < 2) return null
          const labelRadius = MAX_RADIUS + 20
          const x = CENTER_X + labelRadius * Math.cos(data.avgAngle)
          const y = CENTER_Y + labelRadius * Math.sin(data.avgAngle)
          return (
            <div
              key={cat}
              className="absolute text-[9px] text-gray-500 font-medium whitespace-nowrap"
              style={{
                left: x,
                top: y,
                transform: 'translate(-50%, -50%)',
              }}
            >
              {cat} ({data.count})
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default SemanticHeatmap
