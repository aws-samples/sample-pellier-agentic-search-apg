/**
 * RAG Demo — Side-by-side comparison of naive LLM vs RAG-grounded responses.
 * Shows retrieved context and highlights the difference.
 */
import { useState } from 'react'
import Markdown from 'react-markdown'
import { X, Zap, BookOpen, Search, ChevronDown, ChevronUp } from 'lucide-react'
import ProductCardCompact from './ProductCardCompact'

interface RAGProduct {
  id: number
  name: string
  price: number
  rating: number
  category: string
  reviews: number
  image: string
  similarity: number
}

interface RAGResult {
  query: string
  response: string
  retrieved_products: RAGProduct[]
  with_context: boolean
  context_tokens: number
}

interface RAGDemoProps {
  isOpen: boolean
  onClose: () => void
}

const SAMPLE_QUERIES = [
  'What are the best skincare products for dry skin?',
  'Recommend a good laptop for programming',
  'Gift ideas for someone who loves cooking',
  'Comfortable shoes for standing all day',
]

const RAGDemo = ({ isOpen, onClose }: RAGDemoProps) => {
  const [query, setQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [withoutContext, setWithoutContext] = useState<RAGResult | null>(null)
  const [withContext, setWithContext] = useState<RAGResult | null>(null)
  const [showContext, setShowContext] = useState(false)

  const runComparison = async (q?: string) => {
    const searchQuery = q || query
    if (!searchQuery.trim()) return

    setIsLoading(true)
    setQuery(searchQuery)
    try {
      const res = await fetch('/api/rag/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery }),
      })
      if (res.ok) {
        const data = await res.json()
        setWithoutContext(data.without_context)
        setWithContext(data.with_context)
      }
    } catch (error) {
      console.error('RAG comparison failed:', error)
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[95vw] max-w-[1200px] max-h-[90vh] rounded-[20px] flex flex-col overflow-hidden shadow-2xl"
        style={{
          background: 'rgba(0, 0, 0, 0.95)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <div className="flex items-center gap-3">
            <BookOpen className="h-6 w-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }} />
            <div>
              <h2 className="text-xl font-semibold" style={{ color: '#ffffff' }}>RAG Demo</h2>
              <p className="text-xs mt-0.5" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Naive LLM vs Retrieval-Augmented Generation
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
          </button>
        </div>

        {/* Query Input */}
        <div className="px-6 py-4" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="flex gap-3 mb-3">
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyPress={e => e.key === 'Enter' && runComparison()}
              placeholder="Ask a product question..."
              className="flex-1 px-4 py-3 rounded-xl text-sm text-white placeholder-white/30 focus:outline-none"
              style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />
            <button
              onClick={() => runComparison()}
              disabled={isLoading || !query.trim()}
              className="px-6 py-3 rounded-xl font-medium text-sm transition-all disabled:opacity-40 flex items-center gap-2"
              style={{ background: 'rgba(255, 255, 255, 0.1)', border: '1px solid rgba(255, 255, 255, 0.12)', color: '#ffffff' }}
            >
              <Search className="h-4 w-4" />
              {isLoading ? 'Comparing...' : 'Compare'}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Try:</span>
            {SAMPLE_QUERIES.map(sq => (
              <button
                key={sq}
                onClick={() => setQuery(sq)}
                className="text-xs px-3 py-1 rounded-full transition-colors hover:bg-white/10"
                style={{ background: 'rgba(255, 255, 255, 0.06)', border: '1px solid rgba(255, 255, 255, 0.1)', color: 'rgba(255, 255, 255, 0.7)' }}
              >
                {sq.length > 40 ? sq.slice(0, 37) + '...' : sq}
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto px-6 py-6 search-scroll">
          {!withoutContext && !withContext ? (
            <div className="text-center py-16">
              <BookOpen className="h-16 w-16 mx-auto mb-4" style={{ color: 'rgba(255, 255, 255, 0.1)' }} />
              <p style={{ color: 'rgba(255, 255, 255, 0.55)' }}>Ask a product question to compare naive vs RAG responses</p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-6">
                {/* Without Context */}
                <div>
                  <div className="mb-3 p-3 rounded-xl" style={{ background: 'rgba(248, 113, 113, 0.08)', border: '1px solid rgba(248, 113, 113, 0.2)' }}>
                    <h3 className="text-sm font-semibold" style={{ color: '#f87171' }}>Without Context (Naive)</h3>
                    <p className="text-[10px] mt-1" style={{ color: 'rgba(255, 255, 255, 0.55)' }}>LLM responds from training data only — may hallucinate</p>
                  </div>
                  <div className="rag-markdown p-4 rounded-xl text-sm leading-relaxed" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', color: 'rgba(255, 255, 255, 0.9)' }}>
                    <Markdown>{withoutContext?.response || 'Loading...'}</Markdown>
                  </div>
                </div>

                {/* With RAG Context */}
                <div>
                  <div className="mb-3 p-3 rounded-xl" style={{ background: 'rgba(52, 211, 153, 0.08)', border: '1px solid rgba(52, 211, 153, 0.2)' }}>
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-semibold" style={{ color: '#34d399' }}>With RAG (Grounded)</h3>
                      {withContext && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(52, 211, 153, 0.15)', color: '#34d399' }}>
                          {withContext.context_tokens} context tokens
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] mt-1" style={{ color: 'rgba(255, 255, 255, 0.55)' }}>Response grounded in actual product catalog via pgvector retrieval</p>
                  </div>
                  <div className="rag-markdown p-4 rounded-xl text-sm leading-relaxed" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', color: 'rgba(255, 255, 255, 0.9)' }}>
                    <Markdown>{withContext?.response || 'Loading...'}</Markdown>
                  </div>
                </div>
              </div>

              {/* Retrieved Context Accordion */}
              {withContext?.retrieved_products && withContext.retrieved_products.length > 0 && (
                <div className="mt-6">
                  <button
                    onClick={() => setShowContext(!showContext)}
                    className="flex items-center gap-2 text-xs font-medium w-full p-3 rounded-xl transition-colors hover:bg-white/[0.06]"
                    style={{ background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.08)', color: 'rgba(255, 255, 255, 0.75)' }}
                  >
                    <Zap className="h-3.5 w-3.5" />
                    Retrieved Context ({withContext.retrieved_products.length} products)
                    {showContext ? <ChevronUp className="h-3.5 w-3.5 ml-auto" /> : <ChevronDown className="h-3.5 w-3.5 ml-auto" />}
                  </button>
                  {showContext && (
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      {withContext.retrieved_products.map((p, idx) => (
                        <ProductCardCompact
                          key={idx}
                          product={{
                            id: p.id,
                            name: p.name,
                            price: p.price,
                            stars: p.rating,
                            reviews: p.reviews,
                            category: p.category,
                            image: p.image,
                            similarityScore: p.similarity,
                          }}
                          similarityScore={p.similarity}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="flex items-start gap-2 text-xs" style={{ color: 'rgba(255, 255, 255, 0.55)' }}>
            <Zap className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
            <p>
              <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.75)' }}>RAG Pattern</span> — Retrieve relevant products via pgvector,
              augment the prompt with real catalog data, then generate a grounded response. Reduces hallucination.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default RAGDemo
