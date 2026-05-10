/**
 * Context Dashboard — Token usage, prompt versions, cost, and efficiency metrics.
 * Renders as a modal overlay with Apple dark glass aesthetic.
 */
import { useState, useEffect } from 'react'
import { X, Activity, Zap, DollarSign, Clock, TrendingUp, Code, AlertTriangle, Database } from 'lucide-react'

interface ContextStats {
  window_size: number
  current_tokens: number
  usage_percentage: number
  available_tokens: number
  total_messages: number
  system_prompt_tokens: number
  session_duration_minutes: number
  total_tokens_processed: number
  pruning_events: number
  avg_tokens_per_message: number
  estimated_cost_usd: number
  efficiency_score: number
}

interface PromptVersion {
  agent: string
  version: string
  performance: {
    avg_response_time_ms: number
    success_rate: number
  }
}

interface CacheStats {
  cache_size: number
  cache_max: number
  hits: number
  misses: number
  hit_rate: number
  total_requests: number
  total_embedding_cost_usd: number
}

interface ContextDashboardProps {
  isOpen: boolean
  onClose: () => void
  sessionId?: string
}

const ContextDashboard = ({ isOpen, onClose, sessionId }: ContextDashboardProps) => {
  const [stats, setStats] = useState<ContextStats | null>(null)
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([])
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null)

  useEffect(() => {
    if (!isOpen) return

    const fetchStats = async () => {
      try {
        const response = await fetch(`/api/context/stats${sessionId ? `?session_id=${sessionId}` : ''}`)
        if (response.ok) {
          const data = await response.json()
          setStats(data)
        }
      } catch (error) {
        console.error('Failed to fetch context stats:', error)
      }
    }

    const fetchPrompts = async () => {
      try {
        const response = await fetch('/api/context/prompts')
        if (response.ok) {
          const data = await response.json()
          setPromptVersions(data.prompts || [])
        }
      } catch (error) {
        console.error('Failed to fetch prompts:', error)
      }
    }

    const fetchCacheStats = async () => {
      try {
        const response = await fetch('/api/cache/stats')
        if (response.ok) {
          const data = await response.json()
          setCacheStats(data)
        }
      } catch (error) {
        console.error('Failed to fetch cache stats:', error)
      }
    }

    fetchStats()
    fetchPrompts()
    fetchCacheStats()
    const interval = setInterval(() => { fetchStats(); fetchCacheStats() }, 5000)
    return () => clearInterval(interval)
  }, [isOpen, sessionId])

  if (!isOpen) return null

  const getUsageBarStyle = (percentage: number) => {
    if (percentage < 60) return 'rgba(52, 211, 153, 0.5)'
    if (percentage < 85) return 'rgba(251, 191, 36, 0.5)'
    return 'rgba(248, 113, 113, 0.5)'
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[520px] max-h-[85vh] rounded-[20px] shadow-2xl overflow-hidden flex flex-col"
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
            <Activity className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
            <span className="text-sm font-semibold" style={{ color: '#ffffff' }}>Context & Cost</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.35)' }}>Live</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5 search-scroll">
          {!stats ? (
            <div className="text-center py-8">
              <Activity className="h-6 w-6 mx-auto mb-2 animate-pulse" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
              <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>Loading context stats...</p>
            </div>
          ) : (
            <>
              {/* Token Usage Meter */}
              <div className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                    <span className="text-xs font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Context Window</span>
                  </div>
                  <span className="text-sm font-bold" style={{ color: '#ffffff' }}>
                    {stats.current_tokens.toLocaleString()} / 200K
                  </span>
                </div>

                {/* Progress Bar */}
                <div className="h-2.5 rounded-full overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.04)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, stats.usage_percentage)}%`,
                      background: getUsageBarStyle(stats.usage_percentage),
                    }}
                  />
                </div>

                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{stats.usage_percentage.toFixed(1)}% used</span>
                  <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{stats.available_tokens.toLocaleString()} available</span>
                </div>

                {stats.usage_percentage > 85 && (
                  <div className="mt-3 p-2 rounded-lg flex items-start gap-2" style={{ background: 'rgba(251, 191, 36, 0.06)', border: '1px solid rgba(251, 191, 36, 0.15)' }}>
                    <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color: 'rgba(251, 191, 36, 0.6)' }} />
                    <p className="text-[11px]" style={{ color: 'rgba(251, 191, 36, 0.7)' }}>
                      Approaching context limit. Auto-pruning activates at 85%.
                    </p>
                  </div>
                )}
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { icon: <Clock className="h-4 w-4" />, value: stats.total_messages, label: 'Messages', sub: `~${stats.avg_tokens_per_message.toFixed(0)} tok/msg` },
                  { icon: <TrendingUp className="h-4 w-4" />, value: `${stats.efficiency_score.toFixed(0)}%`, label: 'Efficiency', sub: `${stats.pruning_events} prunes` },
                  { icon: <DollarSign className="h-4 w-4" />, value: `$${stats.estimated_cost_usd.toFixed(4)}`, label: 'Cost', sub: 'Input tokens' },
                  { icon: <Clock className="h-4 w-4" />, value: `${stats.session_duration_minutes.toFixed(0)}m`, label: 'Duration', sub: 'Active' },
                ].map((card, idx) => (
                  <div key={idx} className="p-3 rounded-xl text-center" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                    <div className="flex justify-center mb-1.5" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{card.icon}</div>
                    <div className="text-lg font-bold" style={{ color: '#ffffff' }}>{card.value}</div>
                    <div className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{card.label}</div>
                    <div className="text-[9px] mt-0.5" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>{card.sub}</div>
                  </div>
                ))}
              </div>

              {/* Cache Performance */}
              {cacheStats && (
                <div className="p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <Database className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                    <span className="text-xs font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Embedding Cache</span>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    {/* Hit Rate Circle */}
                    <div className="text-center">
                      <div className="relative inline-flex items-center justify-center w-14 h-14">
                        <svg className="w-14 h-14 -rotate-90" viewBox="0 0 56 56">
                          <circle cx="28" cy="28" r="24" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
                          <circle cx="28" cy="28" r="24" fill="none" stroke="rgba(52, 211, 153, 0.6)" strokeWidth="4"
                            strokeDasharray={`${(cacheStats.hit_rate * 100 * 1.508).toFixed(0)} 151`}
                            strokeLinecap="round" />
                        </svg>
                        <span className="absolute text-[11px] font-bold" style={{ color: '#ffffff' }}>
                          {(cacheStats.hit_rate * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="text-[10px] mt-1" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>Hit Rate</div>
                    </div>
                    {/* Cache Size */}
                    <div className="text-center flex flex-col items-center justify-center">
                      <div className="text-lg font-bold" style={{ color: '#ffffff' }}>{cacheStats.cache_size}</div>
                      <div className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>Cached / {cacheStats.cache_max}</div>
                    </div>
                    {/* Embedding Cost */}
                    <div className="text-center flex flex-col items-center justify-center">
                      <div className="text-lg font-bold" style={{ color: '#ffffff' }}>${cacheStats.total_embedding_cost_usd.toFixed(4)}</div>
                      <div className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>Embed Cost</div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-3 pt-2" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
                    <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>{cacheStats.hits} hits / {cacheStats.misses} misses</span>
                    <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>{cacheStats.total_requests} total requests</span>
                  </div>
                </div>
              )}

              {/* Prompt Versions */}
              {promptVersions.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Active Prompt Versions</h3>
                  <div className="space-y-2">
                    {promptVersions.map((prompt) => (
                      <div key={prompt.agent} className="p-3 rounded-xl flex items-center justify-between" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                        <div className="flex items-center gap-2">
                          <Code className="h-3.5 w-3.5" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
                          <span className="text-xs font-medium" style={{ color: 'rgba(255, 255, 255, 0.7)' }}>{prompt.agent}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{prompt.performance.avg_response_time_ms}ms</span>
                          <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{(prompt.performance.success_rate * 100).toFixed(0)}%</span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(255, 255, 255, 0.06)', color: 'rgba(255, 255, 255, 0.5)' }}>
                            {prompt.version}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Cost Breakdown Note */}
              <div className="p-3 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div className="flex items-start gap-2">
                  <Zap className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
                  <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                    <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Context Management</span> — 200K token window with auto-pruning at 85% capacity.
                    Cost based on Haiku input pricing ($0.003/1K tokens). Efficiency score measures token utilization, pruning frequency, and message recency.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default ContextDashboard
