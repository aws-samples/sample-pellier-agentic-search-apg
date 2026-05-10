/**
 * Conversation Memory Indicator — Shows accumulated session context in chat header.
 * Displays categories browsed, price preferences, features mentioned, and query count.
 */
import { useState } from 'react'
import { Brain, X } from 'lucide-react'
import { aggregateSessionPreferences } from '../utils/preferenceExtractor'

interface ConversationMemoryIndicatorProps {
  conversationHistory: Array<{ role: string; content: string }>
}

const ConversationMemoryIndicator = ({ conversationHistory }: ConversationMemoryIndicatorProps) => {
  const [showPopover, setShowPopover] = useState(false)
  const prefs = aggregateSessionPreferences(conversationHistory)

  if (prefs.queryCount === 0) return null

  const badgeLabel = prefs.topCategory
    ? `${prefs.queryCount} queries · ${prefs.topCategory}`
    : `${prefs.queryCount} queries`

  return (
    <div className="relative">
      <button
        onClick={() => setShowPopover(!showPopover)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-medium transition-all hover:scale-105"
        style={{
          background: 'rgba(139, 92, 246, 0.15)',
          border: '1px solid rgba(139, 92, 246, 0.3)',
          color: '#c084fc',
        }}
        title="Session memory"
      >
        <Brain className="h-3 w-3" />
        {badgeLabel}
      </button>

      {/* Popover */}
      {showPopover && (
        <div
          className="absolute top-full left-0 mt-2 w-64 p-4 rounded-xl z-50 animate-slideUp"
          style={{
            background: 'rgba(13, 13, 26, 0.95)',
            border: '1px solid rgba(139, 92, 246, 0.3)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-purple-400" />
              <span className="text-xs font-semibold text-white">Session Memory</span>
            </div>
            <button onClick={() => setShowPopover(false)} className="text-gray-400 hover:text-white">
              <X className="h-3 w-3" />
            </button>
          </div>

          <div className="space-y-2.5">
            {prefs.categories.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-400 mb-1">Categories Browsed</div>
                <div className="flex flex-wrap gap-1">
                  {prefs.categories.map((cat, i) => (
                    <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      {cat}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {prefs.priceRange && (
              <div>
                <div className="text-[10px] text-gray-400 mb-1">Price Preference</div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-500/20 text-green-300 border border-green-500/30">
                  ${prefs.priceRange.min} – ${prefs.priceRange.max}
                </span>
              </div>
            )}

            {prefs.features.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-400 mb-1">Features Mentioned</div>
                <div className="flex flex-wrap gap-1">
                  {prefs.features.map((f, i) => (
                    <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {prefs.qualityPreference && (
              <div>
                <div className="text-[10px] text-gray-400 mb-1">Quality Tier</div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {prefs.qualityPreference}
                </span>
              </div>
            )}

            <div className="pt-2 border-t border-white/10">
              <div className="text-[10px] text-gray-500">
                {prefs.queryCount} queries this session
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ConversationMemoryIndicator
