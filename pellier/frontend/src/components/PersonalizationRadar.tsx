/**
 * Personalization Radar — CSS-only spider chart showing learned user preferences.
 * 5 axes: Price Sensitivity, Brand Loyalty, Category Focus, Quality Priority, Trend Following.
 */
import { useMemo } from 'react'
import { X, User } from 'lucide-react'
import { aggregateSessionPreferences } from '../utils/preferenceExtractor'

interface PersonalizationRadarProps {
  isOpen: boolean
  onClose: () => void
}

const AXES = [
  { label: 'Price\nSensitivity', angle: -90 },
  { label: 'Category\nFocus', angle: -18 },
  { label: 'Trend\nFollowing', angle: 54 },
  { label: 'Quality\nPriority', angle: 126 },
  { label: 'Brand\nLoyalty', angle: 198 },
]

function computeScores(history: Array<{ role: string; content: string }>): number[] {
  const prefs = aggregateSessionPreferences(history)

  // Price Sensitivity: based on budget mentions
  const priceSensitivity = prefs.priceRange ? Math.min(80 + (prefs.queryCount * 3), 100) : Math.min(prefs.queryCount * 10, 40)

  // Category Focus: how concentrated the browsing is
  const categoryFocus = prefs.categories.length === 0 ? 20
    : prefs.categories.length === 1 ? 90
    : prefs.categories.length <= 3 ? 60 : 30

  // Trend Following: presence of trending/popular/best-seller keywords
  const trendKeywords = history.filter(m => m.role === 'user' && /trending|popular|best.?seller|hot|new/i.test(m.content)).length
  const trendFollowing = Math.min(trendKeywords * 25 + 15, 100)

  // Quality Priority: quality/rating keywords
  const qualityKeywords = history.filter(m => m.role === 'user' && /best|top|quality|premium|rated|review/i.test(m.content)).length
  const qualityPriority = Math.min(qualityKeywords * 20 + 15, 100)

  // Brand Loyalty: brand name mentions (simplified)
  const brandKeywords = history.filter(m => m.role === 'user' && /brand|sony|apple|samsung|bose|lg|dell|hp|asus|lenovo/i.test(m.content)).length
  const brandLoyalty = Math.min(brandKeywords * 30 + 10, 100)

  return [priceSensitivity, categoryFocus, trendFollowing, qualityPriority, brandLoyalty]
}

function getPolygonPoints(scores: number[], size: number): string {
  const center = size / 2
  const maxRadius = (size / 2) - 30

  return scores.map((score, i) => {
    const angle = (AXES[i].angle * Math.PI) / 180
    const radius = (score / 100) * maxRadius
    const x = center + radius * Math.cos(angle)
    const y = center + radius * Math.sin(angle)
    return `${x},${y}`
  }).join(' ')
}

const PersonalizationRadar = ({ isOpen, onClose }: PersonalizationRadarProps) => {
  const SIZE = 280
  const CENTER = SIZE / 2
  const MAX_RADIUS = (SIZE / 2) - 30

  const savedHistory = localStorage.getItem('pellier-conversation-history')
  const history = savedHistory ? JSON.parse(savedHistory) : []
  const scores = useMemo(() => computeScores(history), [savedHistory])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[400px] rounded-2xl shadow-2xl border overflow-hidden animate-slideUp"
        style={{
          background: 'linear-gradient(135deg, rgba(17, 24, 39, 0.98) 0%, rgba(31, 41, 55, 0.98) 100%)',
          borderColor: 'rgba(139, 92, 246, 0.3)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b flex items-center justify-between" style={{ borderColor: 'rgba(139, 92, 246, 0.2)' }}>
          <div className="flex items-center gap-2">
            <User className="h-5 w-5 text-purple-400" />
            <span className="text-sm font-semibold text-white">Personalization Radar</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-purple-500/20 transition-colors">
            <X className="h-4 w-4 text-gray-400" />
          </button>
        </div>

        {/* Radar Chart */}
        <div className="flex justify-center py-6">
          <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
            {/* Grid rings */}
            {[0.25, 0.5, 0.75, 1].map((scale, i) => (
              <polygon
                key={i}
                points={AXES.map((_, idx) => {
                  const angle = (AXES[idx].angle * Math.PI) / 180
                  const r = MAX_RADIUS * scale
                  return `${CENTER + r * Math.cos(angle)},${CENTER + r * Math.sin(angle)}`
                }).join(' ')}
                fill="none"
                stroke="rgba(139, 92, 246, 0.15)"
                strokeWidth="1"
              />
            ))}

            {/* Axis lines */}
            {AXES.map((axis, i) => {
              const angle = (axis.angle * Math.PI) / 180
              return (
                <line
                  key={i}
                  x1={CENTER} y1={CENTER}
                  x2={CENTER + MAX_RADIUS * Math.cos(angle)}
                  y2={CENTER + MAX_RADIUS * Math.sin(angle)}
                  stroke="rgba(139, 92, 246, 0.2)"
                  strokeWidth="1"
                />
              )
            })}

            {/* Data polygon */}
            <polygon
              points={getPolygonPoints(scores, SIZE)}
              fill="rgba(168, 85, 247, 0.2)"
              stroke="rgba(168, 85, 247, 0.7)"
              strokeWidth="2"
            />

            {/* Data points */}
            {scores.map((score, i) => {
              const angle = (AXES[i].angle * Math.PI) / 180
              const radius = (score / 100) * MAX_RADIUS
              return (
                <circle
                  key={i}
                  cx={CENTER + radius * Math.cos(angle)}
                  cy={CENTER + radius * Math.sin(angle)}
                  r="4"
                  fill="#a855f7"
                  stroke="white"
                  strokeWidth="1.5"
                />
              )
            })}

            {/* Labels */}
            {AXES.map((axis, i) => {
              const angle = (axis.angle * Math.PI) / 180
              const labelRadius = MAX_RADIUS + 22
              const x = CENTER + labelRadius * Math.cos(angle)
              const y = CENTER + labelRadius * Math.sin(angle)
              const lines = axis.label.split('\n')
              return (
                <text
                  key={i}
                  x={x} y={y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="text-[9px] fill-gray-400"
                >
                  {lines.map((line, li) => (
                    <tspan key={li} x={x} dy={li === 0 ? 0 : 11}>{line}</tspan>
                  ))}
                </text>
              )
            })}
          </svg>
        </div>

        {/* Score summary */}
        <div className="px-5 pb-4 grid grid-cols-5 gap-1">
          {AXES.map((axis, i) => (
            <div key={i} className="text-center">
              <div className="text-lg font-bold text-purple-300">{scores[i]}</div>
              <div className="text-[8px] text-gray-500">{axis.label.replace('\n', ' ')}</div>
            </div>
          ))}
        </div>

        <div className="px-5 pb-4">
          <p className="text-[10px] text-gray-500 text-center">
            Based on {history.filter((m: any) => m.role === 'user').length} queries this session
          </p>
        </div>
      </div>
    </div>
  )
}

export default PersonalizationRadar
