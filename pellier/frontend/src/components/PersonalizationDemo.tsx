/**
 * Personalization Demo — Preference-based re-ranking comparison.
 * Apple dark glass modal showing side-by-side base vs personalized results.
 */
import { useState } from 'react'
import { X, User, Search, Lightbulb, Sliders } from 'lucide-react'

interface PersonalizationDemoProps {
  isOpen: boolean
  onClose: () => void
}

interface Product {
  productId: number
  product_description: string
  price: number
  stars: number
  category_name: string
  similarity?: number
  personalized_score?: number
  personalization_boost?: number
  recommendation_reasons?: string[]
}

const SAMPLE_QUERIES = [
  'gift for someone who loves cooking',
  'luxury watch for a special occasion',
  'comfortable shoes for standing all day',
  'something to make my skin glow',
  'budget laptop for college',
]

const CATEGORY_OPTIONS = [
  'Shoes', 'Watches', 'Laptops', 'Fragrances', 'Sunglasses',
  'Smartphones', 'Bags', 'Furniture', 'Beauty', 'Sports Accessories',
]

const PersonalizationDemo = ({ isOpen, onClose }: PersonalizationDemoProps) => {
  const [query, setQuery] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [maxPrice, setMaxPrice] = useState<number | ''>('')
  const [baseResults, setBaseResults] = useState<Product[]>([])
  const [personalizedResults, setPersonalizedResults] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)

  const toggleCategory = (cat: string) => {
    setSelectedCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    )
  }

  const runComparison = async (q?: string) => {
    const searchQuery = q || query
    if (!searchQuery.trim()) return
    if (q) setQuery(q)
    setLoading(true)

    try {
      // Base search (no preferences)
      const baseRes = await fetch('/api/personalization/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, preferences: {}, limit: 5 }),
      })
      if (baseRes.ok) {
        const data = await baseRes.json()
        setBaseResults(data.products || [])
      }

      // Personalized search (with preferences)
      const preferences: Record<string, any> = {}
      if (selectedCategories.length > 0) preferences.categories = selectedCategories
      if (maxPrice) preferences.price_range = { max: Number(maxPrice) }

      const perRes = await fetch('/api/personalization/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, preferences, limit: 5 }),
      })
      if (perRes.ok) {
        const data = await perRes.json()
        setPersonalizedResults(data.products || [])
      }
    } catch (err) {
      console.error('Personalization comparison failed:', err)
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[820px] max-h-[85vh] rounded-[20px] shadow-2xl overflow-hidden flex flex-col"
        style={{
          background: 'rgba(0, 0, 0, 0.95)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <div className="flex items-center gap-2">
            <User className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
            <span className="text-sm font-semibold" style={{ color: '#ffffff' }}>Personalization Demo</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.35)' }}>Re-ranking</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5 search-scroll">
          {/* Preferences Panel */}
          <div className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <div className="flex items-center gap-2 mb-3">
              <Sliders className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
              <span className="text-xs font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>User Preferences</span>
            </div>

            {/* Category chips */}
            <div className="flex flex-wrap gap-1.5 mb-3">
              {CATEGORY_OPTIONS.map(cat => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className="px-2.5 py-1 rounded-full text-[11px] font-medium transition-all"
                  style={{
                    background: selectedCategories.includes(cat) ? 'rgba(59, 130, 246, 0.3)' : 'rgba(255, 255, 255, 0.06)',
                    border: `1px solid ${selectedCategories.includes(cat) ? 'rgba(59, 130, 246, 0.5)' : 'rgba(255, 255, 255, 0.08)'}`,
                    color: selectedCategories.includes(cat) ? 'rgba(147, 197, 253, 0.9)' : 'rgba(255, 255, 255, 0.5)',
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>

            {/* Price range */}
            <div className="flex items-center gap-2">
              <span className="text-[11px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Max budget:</span>
              <input
                type="number"
                value={maxPrice}
                onChange={e => setMaxPrice(e.target.value ? Number(e.target.value) : '')}
                placeholder="No limit"
                className="w-24 px-2 py-1 rounded-lg text-xs"
                style={{
                  background: 'rgba(255, 255, 255, 0.06)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#ffffff',
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Query input */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && runComparison()}
                placeholder="Search products..."
                className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm"
                style={{
                  background: 'rgba(255, 255, 255, 0.06)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#ffffff',
                  outline: 'none',
                }}
              />
            </div>
            <button
              onClick={() => runComparison()}
              disabled={loading || !query.trim()}
              className="px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40"
              style={{ background: 'rgba(59, 130, 246, 0.3)', color: 'rgba(147, 197, 253, 0.9)', border: '1px solid rgba(59, 130, 246, 0.3)' }}
            >
              {loading ? 'Searching...' : 'Compare'}
            </button>
          </div>

          {/* Sample queries */}
          <div className="flex flex-wrap gap-1.5">
            {SAMPLE_QUERIES.map(q => (
              <button
                key={q}
                onClick={() => runComparison(q)}
                className="px-2.5 py-1 rounded-full text-[11px] transition-all hover:bg-white/10"
                style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.5)' }}
              >
                {q}
              </button>
            ))}
          </div>

          {/* Side-by-side results */}
          {(baseResults.length > 0 || personalizedResults.length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              {/* Base results */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Base Search</h3>
                <div className="space-y-2">
                  {baseResults.map((p, i) => (
                    <div key={p.productId || i} className="p-3 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                      <div className="text-xs font-medium line-clamp-2 mb-1" style={{ color: 'rgba(255, 255, 255, 0.8)' }}>
                        {p.product_description}
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[11px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{p.category_name}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold" style={{ color: '#3b82f6' }}>${p.price?.toFixed(2)}</span>
                          {p.similarity !== undefined && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.35)' }}>
                              {(p.similarity * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Personalized results */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(251, 191, 36, 0.7)' }}>Personalized</h3>
                <div className="space-y-2">
                  {personalizedResults.map((p, i) => (
                    <div key={p.productId || i} className="p-3 rounded-xl" style={{ background: 'rgba(251, 191, 36, 0.03)', border: '1px solid rgba(251, 191, 36, 0.1)' }}>
                      <div className="text-xs font-medium line-clamp-2 mb-1" style={{ color: 'rgba(255, 255, 255, 0.8)' }}>
                        {p.product_description}
                      </div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{p.category_name}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold" style={{ color: '#3b82f6' }}>${p.price?.toFixed(2)}</span>
                          {p.personalized_score !== undefined && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(251, 191, 36, 0.15)', color: 'rgba(251, 191, 36, 0.8)' }}>
                              {(p.personalized_score * 100).toFixed(0)}%
                            </span>
                          )}
                          {p.personalization_boost !== undefined && p.personalization_boost > 0 && (
                            <span className="text-[10px] font-bold" style={{ color: 'rgba(52, 211, 153, 0.8)' }}>
                              +{(p.personalization_boost * 100).toFixed(0)}
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Recommendation reasons */}
                      {p.recommendation_reasons && p.recommendation_reasons.length > 0 && (
                        <div className="mt-1.5 pt-1.5" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.05)' }}>
                          {p.recommendation_reasons.map((reason, ri) => (
                            <div key={ri} className="flex items-start gap-1.5 text-[10px]" style={{ color: 'rgba(251, 191, 36, 0.6)' }}>
                              <Lightbulb className="h-3 w-3 mt-0.5 flex-shrink-0" />
                              <span>{reason}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Educational note */}
          <div className="p-3 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <div className="flex items-start gap-2">
              <Lightbulb className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
              <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Personalization</span> — Re-ranks semantic search results based on user preferences.
                Category matches boost +10%, price range matches +5%, high ratings +3%.
                The boost formula is a Wire It Live exercise for workshop participants.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PersonalizationDemo
