/**
 * Proactive Agent Suggestions — Context-aware floating bar that suggests actions
 * based on browsing behavior and conversation history.
 */
import { useState, useEffect } from 'react'
import { X, Sparkles } from 'lucide-react'
import { aggregateSessionPreferences } from '../utils/preferenceExtractor'
import { getRecentlyViewed } from '../utils/recentlyViewed'
import { useTheme } from '../App'

interface ProactiveSuggestionsProps {
  onSuggestionClick: (query: string) => void
  onDismiss: () => void
}

const ProactiveSuggestions = ({ onSuggestionClick, onDismiss }: ProactiveSuggestionsProps) => {
  const { theme } = useTheme()
  const [suggestions, setSuggestions] = useState<Array<{ text: string; query: string }>>([])
  const [isDismissing, setIsDismissing] = useState(false)

  useEffect(() => {
    const recentlyViewed = getRecentlyViewed()
    const savedHistory = localStorage.getItem('pellier-conversation-history')
    const history = savedHistory ? JSON.parse(savedHistory) : []
    const prefs = aggregateSessionPreferences(history)

    const generated: Array<{ text: string; query: string }> = []

    // Based on recently viewed categories
    if (recentlyViewed.length >= 2) {
      generated.push({
        text: `Compare your ${recentlyViewed.length} recently viewed items`,
        query: 'Compare my recently viewed products'
      })
    }

    // Based on conversation preferences
    if (prefs.categories.length > 0) {
      generated.push({
        text: `Trending in ${prefs.categories[0]}`,
        query: `Show me trending ${prefs.categories[0].toLowerCase()} products`
      })
    }

    if (prefs.priceRange) {
      generated.push({
        text: `Best deals under $${prefs.priceRange.max}`,
        query: `Best deals under $${prefs.priceRange.max}`
      })
    }

    if (prefs.features.length > 0) {
      generated.push({
        text: `More ${prefs.features[0]} options`,
        query: `Show me more ${prefs.features[0]} products`
      })
    }

    setSuggestions(generated.slice(0, 3))
  }, [])

  if (suggestions.length === 0) return null

  const handleDismiss = () => {
    setIsDismissing(true)
    setTimeout(onDismiss, 300)
  }

  return (
    <div
      className="fixed top-[80px] left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-4 py-2.5 rounded-full"
      style={{
        background: theme === 'dark' ? 'rgba(0, 0, 0, 0.95)' : 'rgba(255, 255, 255, 0.97)',
        border: '1px solid var(--border-color)',
        backdropFilter: 'blur(20px)',
        boxShadow: theme === 'dark' ? '0 8px 32px rgba(0, 0, 0, 0.3)' : '0 8px 32px rgba(0, 0, 0, 0.1)',
        transform: isDismissing ? 'translate(-50%, -20px)' : 'translate(-50%, 0)',
        opacity: isDismissing ? 0 : 1,
        transition: 'all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
      }}
    >
      <Sparkles className="h-4 w-4 text-text-secondary flex-shrink-0" />
      <div className="flex items-center gap-2">
        {suggestions.map((s, idx) => (
          <button
            key={idx}
            onClick={() => onSuggestionClick(s.query)}
            className="px-3 py-1 rounded-full text-xs font-medium transition-all hover:scale-105 whitespace-nowrap"
            style={{
              background: 'var(--input-bg)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-secondary)',
            }}
          >
            {s.text}
          </button>
        ))}
      </div>
      <button onClick={handleDismiss} className="p-1 rounded-full transition-colors flex-shrink-0" style={{ ['--tw-bg-opacity' as any]: 1 }} onMouseEnter={(e) => e.currentTarget.style.background = 'var(--input-bg)'} onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
        <X className="h-3 w-3 text-text-secondary" />
      </button>
    </div>
  )
}

export default ProactiveSuggestions
