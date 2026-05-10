/**
 * Agent Activity Dashboard — Aggregates session stats from conversation history.
 * Shows query counts, agent distribution, products found, and an animated flow diagram.
 */
import { useState, useEffect } from 'react'
import { X, Activity, MessageSquare, Package, Clock, BarChart3 } from 'lucide-react'
import { AGENT_IDENTITIES, type AgentType } from '../utils/agentIdentity'

interface AgentActivityDashboardProps {
  isOpen: boolean
  onClose: () => void
}

interface SessionStats {
  totalQueries: number
  totalProducts: number
  agentDistribution: Record<string, number>
  avgResponseTime: number
  topAgent: string | null
}

function computeStatsFromLocalStorage(): SessionStats {
  const savedHistory = localStorage.getItem('pellier-conversation-history')
  const messages = savedHistory ? JSON.parse(savedHistory) : []

  let totalQueries = 0
  let totalProducts = 0
  const agentCounts: Record<string, number> = {}
  let totalDuration = 0
  let durationCount = 0

  for (const msg of messages) {
    if (msg.role === 'user') totalQueries++
    if (msg.role === 'assistant') {
      if (msg.products?.length) totalProducts += msg.products.length
      if (msg.agent) {
        agentCounts[msg.agent] = (agentCounts[msg.agent] || 0) + 1
      }
      if (msg.agentExecution?.total_duration_ms) {
        totalDuration += msg.agentExecution.total_duration_ms
        durationCount++
      }
    }
  }

  const topAgent = Object.entries(agentCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || null

  return {
    totalQueries,
    totalProducts,
    agentDistribution: agentCounts,
    avgResponseTime: durationCount > 0 ? Math.round(totalDuration / durationCount) : 0,
    topAgent,
  }
}

const AgentActivityDashboard = ({ isOpen, onClose }: AgentActivityDashboardProps) => {
  const [stats, setStats] = useState<SessionStats>(computeStatsFromLocalStorage)

  useEffect(() => {
    if (!isOpen) return
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/agent/stats')
        if (response.ok) {
          const data = await response.json()
          if (data.query_count > 0) {
            setStats({
              totalQueries: data.query_count,
              totalProducts: data.products_found,
              agentDistribution: data.agent_calls_by_type || {},
              avgResponseTime: data.avg_response_time_ms || 0,
              topAgent: Object.entries(data.agent_calls_by_type || {}).sort((a: any, b: any) => b[1] - a[1])[0]?.[0] || null,
            })
            return
          }
        }
      } catch { /* fallback */ }
      setStats(computeStatsFromLocalStorage())
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [isOpen])

  if (!isOpen) return null

  const totalAgentCalls = Object.values(stats.agentDistribution).reduce((a, b) => a + b, 0)

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
            <span className="text-sm font-semibold" style={{ color: '#ffffff' }}>Agent Activity</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5 search-scroll">
          {/* Stats Cards */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { icon: <MessageSquare className="h-4 w-4" />, value: stats.totalQueries, label: 'Queries' },
              { icon: <Package className="h-4 w-4" />, value: stats.totalProducts, label: 'Products' },
              { icon: <BarChart3 className="h-4 w-4" />, value: totalAgentCalls, label: 'Agent Calls' },
              { icon: <Clock className="h-4 w-4" />, value: stats.avgResponseTime, label: 'Avg ms' },
            ].map((card, idx) => (
              <div key={idx} className="p-3 rounded-xl text-center" style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div className="flex justify-center mb-1.5" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{card.icon}</div>
                <div className="text-xl font-bold" style={{ color: '#ffffff' }}>{card.value}</div>
                <div className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.35)' }}>{card.label}</div>
              </div>
            ))}
          </div>

          {/* Agent Distribution */}
          {totalAgentCalls > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Agent Distribution</h3>
              <div className="space-y-2">
                {Object.entries(stats.agentDistribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([agent, count]) => {
                    const identity = AGENT_IDENTITIES[agent as AgentType]
                    const pct = Math.round((count / totalAgentCalls) * 100)
                    return (
                      <div key={agent} className="flex items-center gap-3">
                        <div className="flex items-center gap-1.5 w-32">
                          <span className="text-sm">{identity?.icon || 'AI'}</span>
                          <span className="text-xs truncate" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>{identity?.name || agent}</span>
                        </div>
                        <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: 'rgba(255, 255, 255, 0.04)' }}>
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${pct}%`,
                              background: 'rgba(255, 255, 255, 0.15)',
                            }}
                          />
                        </div>
                        <span className="text-xs w-10 text-right" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{pct}%</span>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}

          {/* Animated Flow Diagram */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>Query Flow</h3>
            <div className="flex items-center justify-center gap-2 p-4 rounded-xl" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
              {/* User */}
              <div className="flex flex-col items-center gap-1">
                <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'rgba(255, 255, 255, 0.06)', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                  <MessageSquare className="h-4 w-4" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
                </div>
                <span className="text-[9px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>User</span>
              </div>

              <svg width="30" height="12" className="flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.15)' }}>
                <line x1="0" y1="6" x2="22" y2="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" />
                <polygon points="22,2 28,6 22,10" fill="currentColor" />
              </svg>

              {/* Orchestrator */}
              <div className="flex flex-col items-center gap-1">
                <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'rgba(255, 255, 255, 0.06)', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                  <span className="text-sm font-bold" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>O</span>
                </div>
                <span className="text-[9px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>Orchestrator</span>
              </div>

              <svg width="30" height="12" className="flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.15)' }}>
                <line x1="0" y1="6" x2="22" y2="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" />
                <polygon points="22,2 28,6 22,10" fill="currentColor" />
              </svg>

              {/* Agents stack */}
              <div className="flex flex-col items-center gap-1">
                <div className="flex -space-x-2">
                  {(['recommendation', 'pricing', 'inventory'] as AgentType[]).map(a => (
                    <div key={a} className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'rgba(255, 255, 255, 0.06)', border: '2px solid rgba(0, 0, 0, 0.9)' }}>
                      <span className="text-xs">{AGENT_IDENTITIES[a].icon}</span>
                    </div>
                  ))}
                </div>
                <span className="text-[9px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>Specialists</span>
              </div>

              <svg width="30" height="12" className="flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.15)' }}>
                <line x1="0" y1="6" x2="22" y2="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 3" />
                <polygon points="22,2 28,6 22,10" fill="currentColor" />
              </svg>

              {/* Products */}
              <div className="flex flex-col items-center gap-1">
                <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'rgba(52, 211, 153, 0.08)', border: '1px solid rgba(52, 211, 153, 0.15)' }}>
                  <Package className="h-4 w-4" style={{ color: 'rgba(52, 211, 153, 0.6)' }} />
                </div>
                <span className="text-[9px]" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>Products</span>
              </div>
            </div>
          </div>

          {stats.totalQueries === 0 && (
            <div className="text-center py-4">
              <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.3)' }}>No activity yet. Start chatting with the AI Assistant.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AgentActivityDashboard
