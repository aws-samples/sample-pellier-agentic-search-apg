/**
 * CacheMetricsPanel — Full-screen overlay showing detailed Valkey/ElastiCache stats.
 * Same modal pattern as IndexPerformanceDashboard.
 */
import { useState, useEffect } from 'react'
import { X, Zap, RefreshCw, Database, Clock, Server, ArrowUpRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

interface CacheStats {
  mode: string
  hits: number
  misses: number
  sets: number
  hit_rate: number
  total_keys: number
  uptime_seconds: number
  default_ttl: number
  valkey_memory_used?: string
  valkey_connected_clients?: number
  valkey_keyspace_hits?: number
  valkey_keyspace_misses?: number
  embedding?: {
    total_embedding_cost_usd: number
    hits: number
    misses: number
    hit_rate: number
  }
}

export default function CacheMetricsPanel({ onClose }: { onClose: () => void }) {
  const [stats, setStats] = useState<CacheStats | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStats = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/cache/stats`)
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch {
      // Backend may not be running
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 8000)
    return () => clearInterval(interval)
  }, [])

  const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  const hitRatePercent = stats ? Math.round(stats.hit_rate * 100) : 0

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[200] flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

        {/* Panel */}
        <motion.div
          className="relative w-full max-w-[720px] max-h-[85vh] overflow-y-auto rounded-2xl mx-4"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border-color)',
            boxShadow: '0 25px 80px rgba(0, 0, 0, 0.5)',
          }}
          initial={{ opacity: 0, y: 30, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.97 }}
          transition={{ type: 'spring', stiffness: 200, damping: 25 }}
        >
          {/* Header */}
          <div className="sticky top-0 z-10 px-7 py-5 flex items-center justify-between"
            style={{
              background: 'var(--bg-primary)',
              borderBottom: '1px solid var(--border-color)',
            }}
          >
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl" style={{ background: 'rgba(245,158,11,0.12)' }}>
                <Zap className="h-5 w-5" style={{ color: '#f59e0b' }} />
              </div>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Cache Metrics</h2>
                <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {stats?.mode === 'valkey' ? 'ElastiCache / Valkey' : stats?.mode === 'memory' ? 'In-Memory (Local)' : 'Loading...'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={fetchStats} className="p-2 rounded-lg transition-colors hover:bg-white/5" style={{ color: 'var(--text-tertiary)' }}>
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button onClick={onClose} className="p-2 rounded-lg transition-colors hover:bg-white/5" style={{ color: 'var(--text-tertiary)' }}>
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="p-7 space-y-6">
            {loading && !stats ? (
              <div className="text-center py-12">
                <RefreshCw className="h-8 w-8 mx-auto mb-3 animate-spin" style={{ color: 'var(--text-tertiary)' }} />
                <p style={{ color: 'var(--text-tertiary)' }}>Loading cache metrics...</p>
              </div>
            ) : !stats ? (
              <div className="text-center py-12">
                <Database className="h-8 w-8 mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
                <p style={{ color: 'var(--text-tertiary)' }}>Unable to connect to cache service</p>
              </div>
            ) : (
              <>
                {/* Metric Cards Row */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Hit Rate', value: `${hitRatePercent}%`, icon: <ArrowUpRight className="h-3.5 w-3.5" />, color: '#22c55e' },
                    { label: 'Total Keys', value: `${stats.total_keys}`, icon: <Database className="h-3.5 w-3.5" />, color: '#3b82f6' },
                    { label: 'Uptime', value: formatUptime(stats.uptime_seconds), icon: <Clock className="h-3.5 w-3.5" />, color: '#a855f7' },
                    { label: 'Default TTL', value: `${stats.default_ttl}s`, icon: <Server className="h-3.5 w-3.5" />, color: '#f59e0b' },
                  ].map((m) => (
                    <div key={m.label} className="rounded-xl p-4"
                      style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}
                    >
                      <div className="flex items-center gap-1.5 mb-2">
                        <span style={{ color: m.color }}>{m.icon}</span>
                        <span className="text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>{m.label}</span>
                      </div>
                      <span className="text-xl font-bold tabular-nums" style={{ color: 'var(--text-primary)' }}>{m.value}</span>
                    </div>
                  ))}
                </div>

                {/* Hit Rate Bar */}
                <div className="rounded-xl p-5" style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Cache Performance</span>
                    <span className="text-xs tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
                      {stats.hits} hits / {stats.misses} misses / {stats.sets} sets
                    </span>
                  </div>
                  <div className="w-full h-3 rounded-full overflow-hidden" style={{ background: 'var(--border-color)' }}>
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${hitRatePercent}%`,
                        background: hitRatePercent > 70 ? '#22c55e' : hitRatePercent > 40 ? '#f59e0b' : '#ef4444',
                      }}
                    />
                  </div>
                </div>

                {/* Valkey-specific stats */}
                {stats.mode === 'valkey' && (
                  <div className="rounded-xl p-5" style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Valkey Server</h3>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Memory Used</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.valkey_memory_used ?? 'N/A'}</p>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Connected Clients</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.valkey_connected_clients ?? 'N/A'}</p>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Keyspace Hits</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.valkey_keyspace_hits ?? 'N/A'}</p>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Keyspace Misses</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.valkey_keyspace_misses ?? 'N/A'}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Embedding Cost */}
                {stats.embedding && (
                  <div className="rounded-xl p-5" style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Embedding Cache</h3>
                    <div className="grid grid-cols-3 gap-3 text-sm">
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>API Cost</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>${stats.embedding.total_embedding_cost_usd.toFixed(4)}</p>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Cache Hits</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.embedding.hits}</p>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-tertiary)' }}>Cache Misses</span>
                        <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{stats.embedding.misses}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* About section */}
                <div className="rounded-xl p-5" style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.15)' }}>
                  <h3 className="text-sm font-semibold mb-2" style={{ color: '#fbbf24' }}>About Valkey / ElastiCache</h3>
                  <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    Amazon ElastiCache with Valkey provides sub-millisecond caching for search results
                    and embeddings. In this workshop, the cache layer sits between the Strands agent and
                    Aurora PostgreSQL, reducing database load and Bedrock API calls. When <code className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--input-bg)' }}>VALKEY_URL</code> is
                    set, caching is distributed across nodes; otherwise, a local in-memory store is used as fallback.
                  </p>
                </div>
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
