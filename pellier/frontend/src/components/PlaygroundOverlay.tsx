/**
 * PlaygroundOverlay — Simulation Playground
 * Apple-grade professional design: large typography, generous spacing,
 * interactive simulation cards with rich descriptions and launch actions.
 */
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Shield, ArrowRight, Layers, Zap, Database, Brain, Cpu, Server, Sparkles } from 'lucide-react'
import { useLayout } from '../contexts/LayoutContext'

const MODE_ORDER = ['legacy', 'search', 'agentic', 'production'] as const

interface ToolButton {
  icon: React.ReactNode
  label: string
  desc: string
  tryHint?: string
  action: () => void
  minMode: typeof MODE_ORDER[number]
  group: string
}

interface LabSection {
  key: string
  label: string
  desc: string
  minMode: typeof MODE_ORDER[number]
  intro: string
}

interface ArchDiagram {
  title: string
  img: string
}

interface PlaygroundOverlayProps {
  isVisible: boolean
  onClose: () => void
  devToolButtons: ToolButton[]
  labSections: LabSection[]
  archDiagrams: ArchDiagram[]
  onArchDiagram: (img: string) => void
  chaosMode: boolean
  onModeSwitch: (mode: typeof MODE_ORDER[number]) => void
}

const MODE_META: Record<string, { label: string; desc: string; color: string; step: string }> = {
  legacy: { label: 'Keyword Search', desc: 'The Starting Point', color: '#86868b', step: 'Module 0' },
  search: { label: 'Smart Search', desc: 'Teaching Your Database to Think', color: '#0071e3', step: 'Module 1' },
  agentic: { label: 'Agentic AI', desc: 'Tools, Agents, and Orchestration', color: '#7c3aed', step: 'Module 2' },
  production: { label: 'Production', desc: 'Policies, Memory, and Runtime', color: '#1db954', step: 'Module 3' },
}

const LAB_COLORS: Record<string, string> = {
  lab1: '#0071e3',
  lab2: '#7c3aed',
  lab3: '#1db954',
}

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

export default function PlaygroundOverlay({
  isVisible,
  onClose,
  devToolButtons,
  labSections,
  archDiagrams,
  onArchDiagram,
  onModeSwitch,
}: PlaygroundOverlayProps) {
  const { workshopMode, guardrailsEnabled, setGuardrailsEnabled } = useLayout()
  const [cacheStats, setCacheStats] = useState<{
    mode: string; hits: number; misses: number; hit_rate: number; total_keys: number
  } | null>(null)

  useEffect(() => {
    if (!isVisible) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isVisible, onClose])

  useEffect(() => {
    if (!isVisible || workshopMode !== 'production') return
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/cache/stats`)
        if (res.ok) setCacheStats(await res.json())
      } catch { /* backend may not be running */ }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 10000)
    return () => clearInterval(interval)
  }, [isVisible, workshopMode])

  const hitRatePercent = cacheStats ? Math.round(cacheStats.hit_rate * 100) : 0

  return (
    <AnimatePresence>
      {isVisible && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-[60]"
            style={{ background: 'rgba(0, 0, 0, 0.3)', backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed inset-x-0 top-[72px] bottom-0 z-[61] flex flex-col"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 34 }}
          >
            <div
              className="flex flex-col flex-1 min-h-0 mx-3 sm:mx-5 mt-2 mb-4 rounded-2xl overflow-hidden"
              style={{
                background: '#ffffff',
                boxShadow: '0 0 0 1px rgba(0,0,0,0.04), 0 8px 40px rgba(0,0,0,0.12), 0 24px 80px rgba(0,0,0,0.08)',
              }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-8 sm:px-10 py-6 flex-shrink-0"
                style={{ borderBottom: '1px solid #f0f0f0' }}
              >
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight" style={{ color: '#1d1d1f', letterSpacing: '-0.02em' }}>
                    Simulation Playground
                  </h2>
                  <p className="text-[15px] mt-1" style={{ color: '#86868b' }}>
                    Interactive tools and live demos for each workshop lab
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="p-2.5 rounded-full transition-all duration-200 hover:bg-black/5 active:scale-95"
                >
                  <X className="h-5 w-5" style={{ color: '#86868b' }} />
                </button>
              </div>

              {/* Workshop mode navigation */}
              <div
                className="flex items-center gap-0 px-8 sm:px-10 flex-shrink-0 overflow-x-auto"
                style={{ borderBottom: '1px solid #f0f0f0' }}
              >
                {MODE_ORDER.map((mode) => {
                  const isCurrent = workshopMode === mode
                  const info = MODE_META[mode]
                  return (
                    <button
                      key={mode}
                      onClick={() => onModeSwitch(mode)}
                      className="relative flex flex-col items-start px-5 py-4 text-left transition-all duration-200 flex-shrink-0"
                    >
                      <span className="text-[11px] font-medium uppercase tracking-wider mb-0.5" style={{ color: isCurrent ? info.color : '#c7c7cc', letterSpacing: '0.08em' }}>
                        {info.step}
                      </span>
                      <span className="text-[15px] font-medium" style={{ color: isCurrent ? '#1d1d1f' : '#86868b' }}>
                        {info.label}
                      </span>
                      {/* Active indicator */}
                      {isCurrent && (
                        <motion.div
                          className="absolute bottom-0 left-5 right-5 h-[2px] rounded-full"
                          style={{ background: info.color }}
                          layoutId="activeTab"
                          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                        />
                      )}
                    </button>
                  )
                })}
              </div>

              {/* Scrollable content */}
              <div className="flex-1 min-h-0 overflow-y-auto px-8 sm:px-10 py-8 space-y-10 search-scroll" style={{ background: '#fafafa' }}>
                {/* Lab sections */}
                {labSections
                  .filter(section => section.minMode === workshopMode)
                  .map((section) => {
                    const sectionTools = devToolButtons.filter(b => b.group === section.key)
                    if (sectionTools.length === 0) return null
                    const accent = LAB_COLORS[section.key] || '#1d1d1f'

                    return (
                      <motion.div
                        key={section.key}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                      >
                        {/* Section header */}
                        <div className="flex items-start justify-between mb-6">
                          <div>
                            <div className="flex items-center gap-3 mb-2">
                              <div className="w-8 h-[3px] rounded-full" style={{ background: accent }} />
                              <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: accent, letterSpacing: '0.1em' }}>
                                {section.desc}
                              </span>
                            </div>
                            <h3 className="text-[28px] font-semibold tracking-tight" style={{ color: '#1d1d1f', letterSpacing: '-0.02em' }}>
                              {section.label}
                            </h3>
                          </div>

                          {/* Guardrails toggle */}
                          {section.key === 'lab2' && (
                            <button
                              onClick={() => setGuardrailsEnabled(!guardrailsEnabled)}
                              className="flex items-center gap-3 px-4 py-2.5 rounded-full transition-all duration-200 mt-2"
                              style={{
                                background: guardrailsEnabled ? 'rgba(30, 185, 84, 0.08)' : '#f5f5f7',
                                border: `1px solid ${guardrailsEnabled ? 'rgba(30, 185, 84, 0.25)' : '#e5e5ea'}`,
                              }}
                            >
                              <Shield className="h-4 w-4" style={{ color: guardrailsEnabled ? '#1db954' : '#86868b' }} />
                              <span className="text-[13px] font-medium" style={{ color: guardrailsEnabled ? '#1db954' : '#6e6e73' }}>
                                Guardrails {guardrailsEnabled ? 'On' : 'Off'}
                              </span>
                              <div
                                className="w-9 h-[22px] rounded-full relative transition-colors duration-200 flex-shrink-0"
                                style={{ background: guardrailsEnabled ? '#1db954' : '#d1d1d6' }}
                              >
                                <div
                                  className="absolute top-[3px] w-4 h-4 rounded-full bg-white transition-transform duration-200"
                                  style={{
                                    transform: guardrailsEnabled ? 'translateX(17px)' : 'translateX(3px)',
                                    boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
                                  }}
                                />
                              </div>
                            </button>
                          )}
                        </div>

                        {/* Section intro */}
                        <p className="text-[16px] leading-[1.6] mb-8 max-w-[720px]" style={{ color: '#6e6e73' }}>
                          {section.intro}
                        </p>

                        {/* Simulation cards */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                          {sectionTools.map((tool, idx) => (
                            <motion.button
                              key={idx}
                              onClick={() => { tool.action(); onClose() }}
                              className="text-left rounded-2xl transition-all duration-200 group relative overflow-hidden"
                              style={{
                                background: '#ffffff',
                                border: '1px solid #e5e5ea',
                              }}
                              whileHover={{
                                scale: 1.005,
                                boxShadow: '0 8px 30px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.03)',
                                borderColor: '#d1d1d6',
                              }}
                              whileTap={{ scale: 0.995 }}
                            >
                              <div className="p-6">
                                {/* Icon and title row */}
                                <div className="flex items-center gap-3 mb-3">
                                  <span style={{ color: accent }}>
                                    {tool.icon}
                                  </span>
                                  <h4 className="text-[18px] font-semibold" style={{ color: '#1d1d1f', letterSpacing: '-0.01em' }}>
                                    {tool.label}
                                  </h4>
                                  <ArrowRight
                                    className="h-4 w-4 ml-auto opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:translate-x-0.5"
                                    style={{ color: accent }}
                                  />
                                </div>

                                {/* Description */}
                                <p className="text-[15px] leading-[1.5] mb-4" style={{ color: '#6e6e73' }}>
                                  {tool.desc}
                                </p>

                                {/* Try hint as interactive callout */}
                                {tool.tryHint && (
                                  <div
                                    className="flex items-start gap-2.5 px-4 py-3 rounded-xl"
                                    style={{ background: '#f5f5f7', border: '1px solid #ebebf0' }}
                                  >
                                    <Sparkles className="h-4 w-4 flex-shrink-0 mt-0.5" style={{ color: accent }} />
                                    <p className="text-[13px] leading-[1.5]" style={{ color: '#48484a' }}>
                                      <span className="font-semibold" style={{ color: accent }}>Try it</span>
                                      {' — '}{tool.tryHint}
                                    </p>
                                  </div>
                                )}
                              </div>

                              {/* Bottom accent bar on hover */}
                              <div
                                className="h-[2px] w-full opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                                style={{ background: `linear-gradient(90deg, ${accent}, ${accent}40)` }}
                              />
                            </motion.button>
                          ))}
                        </div>
                      </motion.div>
                    )
                  })}

                {/* Architecture section — agentcore only */}
                {workshopMode === 'production' && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
                  >
                    <div className="mb-6">
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-8 h-[3px] rounded-full" style={{ background: '#1db954' }} />
                        <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: '#1db954', letterSpacing: '0.1em' }}>
                          Live Infrastructure
                        </span>
                      </div>
                      <h3 className="text-[28px] font-semibold tracking-tight" style={{ color: '#1d1d1f', letterSpacing: '-0.02em' }}>
                        System Architecture
                      </h3>
                      <p className="text-[16px] leading-[1.6] mt-2 max-w-[720px]" style={{ color: '#6e6e73' }}>
                        Real-time view of the production pipeline — trace how requests flow through FastAPI, the Strands Agent SDK, Aurora PostgreSQL, Amazon Bedrock, and the AgentCore runtime.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {/* Architecture diagram */}
                      <div className="rounded-2xl p-6" style={{
                        background: '#ffffff',
                        border: '1px solid #e5e5ea',
                      }}>
                        <p className="text-[12px] font-semibold uppercase tracking-wider mb-5" style={{ color: '#86868b', letterSpacing: '0.08em' }}>
                          Production Pipeline
                        </p>
                        <svg viewBox="0 0 360 240" className="w-full h-auto" xmlns="http://www.w3.org/2000/svg">
                          <line x1="55" y1="35" x2="55" y2="70" stroke="#d1d1d6" strokeWidth="1.5" strokeDasharray="4 4">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
                          </line>
                          <line x1="55" y1="100" x2="55" y2="135" stroke="#d1d1d6" strokeWidth="1.5" strokeDasharray="4 4">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
                          </line>
                          <line x1="30" y1="165" x2="30" y2="200" stroke="#0071e3" strokeWidth="1.5" strokeDasharray="4 4" strokeOpacity="0.5">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1.2s" repeatCount="indefinite" />
                          </line>
                          <line x1="100" y1="165" x2="100" y2="200" stroke="#7c3aed" strokeWidth="1.5" strokeDasharray="4 4" strokeOpacity="0.5">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1.2s" repeatCount="indefinite" />
                          </line>
                          <line x1="140" y1="150" x2="200" y2="150" stroke="#e67e00" strokeWidth="1.5" strokeDasharray="4 4" strokeOpacity="0.5">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="0.8s" repeatCount="indefinite" />
                          </line>
                          <line x1="140" y1="85" x2="200" y2="85" stroke="#1db954" strokeWidth="1.5" strokeDasharray="4 4" strokeOpacity="0.5">
                            <animate attributeName="stroke-dashoffset" from="8" to="0" dur="1s" repeatCount="indefinite" />
                          </line>

                          <rect x="20" y="15" width="70" height="24" rx="8" fill="#ffffff" stroke="#d1d1d6" strokeWidth="1" />
                          <text x="55" y="31" textAnchor="middle" fill="#1d1d1f" fontSize="10" fontWeight="500">User</text>

                          <rect x="10" y="72" width="90" height="28" rx="8" fill="#f0f5ff" stroke="#0071e3" strokeWidth="1" strokeOpacity="0.3" />
                          <circle cx="20" cy="86" r="2.5" fill="#1db954" />
                          <text x="58" y="90" textAnchor="middle" fill="#1d1d1f" fontSize="10" fontWeight="500">FastAPI</text>

                          <rect x="5" y="135" width="135" height="28" rx="8" fill="#f5f0ff" stroke="#7c3aed" strokeWidth="1" strokeOpacity="0.3" />
                          <circle cx="15" cy="149" r="2.5" fill="#1db954" />
                          <text x="75" y="153" textAnchor="middle" fill="#1d1d1f" fontSize="10" fontWeight="500">Strands Agent SDK</text>

                          <rect x="0" y="200" width="58" height="34" rx="8" fill="#f0f5ff" stroke="#0071e3" strokeWidth="1" strokeOpacity="0.3" />
                          <text x="29" y="216" textAnchor="middle" fill="#0071e3" fontSize="9" fontWeight="500">Aurora</text>
                          <text x="29" y="228" textAnchor="middle" fill="#86868b" fontSize="7">pgvector</text>

                          <rect x="70" y="200" width="62" height="34" rx="8" fill="#f5f0ff" stroke="#7c3aed" strokeWidth="1" strokeOpacity="0.3" />
                          <text x="101" y="216" textAnchor="middle" fill="#7c3aed" fontSize="9" fontWeight="500">Bedrock</text>
                          <text x="101" y="228" textAnchor="middle" fill="#86868b" fontSize="7">Claude + Cohere</text>

                          <rect x="200" y="132" width="148" height="36" rx="8" fill="#fff8ee" stroke="#e67e00" strokeWidth="1" strokeOpacity="0.3" />
                          <circle cx="212" cy="147" r="2.5" fill="#1db954" />
                          <text x="280" y="148" textAnchor="middle" fill="#e67e00" fontSize="9" fontWeight="500">Valkey / ElastiCache</text>
                          <text x="280" y="160" textAnchor="middle" fill="#86868b" fontSize="7">
                            {cacheStats ? `${hitRatePercent}% hit rate · ${cacheStats.total_keys} keys` : 'connecting...'}
                          </text>

                          <rect x="200" y="48" width="148" height="74" rx="10" fill="#f0faf4" stroke="#1db954" strokeWidth="1" strokeOpacity="0.25" />
                          <text x="274" y="64" textAnchor="middle" fill="#1db954" fontSize="9" fontWeight="600" letterSpacing="0.06em">AGENTCORE</text>
                          {[
                            { label: 'Memory', y: 78, color: '#e11d48' },
                            { label: 'Gateway (MCP)', y: 90, color: '#0891b2' },
                            { label: 'Cedar Policy', y: 102, color: '#1db954' },
                            { label: 'Runtime (Lambda)', y: 114, color: '#e67e00' },
                          ].map((item, i) => (
                            <g key={i}>
                              <circle cx="214" cy={item.y} r="2" fill={item.color} opacity="0.8" />
                              <text x="222" y={item.y + 3} fill="#6e6e73" fontSize="8">{item.label}</text>
                            </g>
                          ))}
                        </svg>
                      </div>

                      {/* Live metrics */}
                      <div className="space-y-4">
                        {/* Cache hit rate */}
                        <div className="rounded-2xl p-6" style={{
                          background: '#ffffff',
                          border: '1px solid #e5e5ea',
                        }}>
                          <div className="flex items-center justify-between mb-4">
                            <div>
                              <p className="text-[12px] font-semibold uppercase tracking-wider mb-1" style={{ color: '#86868b', letterSpacing: '0.08em' }}>Cache Performance</p>
                              <p className="text-[18px] font-semibold" style={{ color: '#1d1d1f' }}>Hit Rate</p>
                            </div>
                            <span className="text-[36px] font-bold tabular-nums" style={{ color: '#e67e00', letterSpacing: '-0.02em' }}>
                              {cacheStats ? `${hitRatePercent}%` : '--'}
                            </span>
                          </div>
                          <div className="w-full h-3 rounded-full overflow-hidden" style={{ background: '#f0f0f0' }}>
                            <div className="h-full rounded-full transition-all duration-700"
                              style={{ width: `${hitRatePercent}%`, background: 'linear-gradient(90deg, #e67e00, #f59e0b)' }}
                            />
                          </div>
                          <div className="flex justify-between mt-3 text-[13px]" style={{ color: '#86868b' }}>
                            <span>{cacheStats?.hits ?? 0} hits / {cacheStats?.misses ?? 0} misses</span>
                            <span>{cacheStats?.total_keys ?? 0} keys cached</span>
                          </div>
                        </div>

                        {/* Service health */}
                        <div className="rounded-2xl p-6" style={{
                          background: '#ffffff',
                          border: '1px solid #e5e5ea',
                        }}>
                          <p className="text-[12px] font-semibold uppercase tracking-wider mb-1" style={{ color: '#86868b', letterSpacing: '0.08em' }}>Infrastructure</p>
                          <p className="text-[18px] font-semibold mb-4" style={{ color: '#1d1d1f' }}>Service Health</p>
                          <div className="grid grid-cols-2 gap-3">
                            {[
                              { name: 'Aurora PostgreSQL', icon: <Database className="h-4 w-4" />, color: '#0071e3', ms: '~12ms' },
                              { name: 'Amazon Bedrock', icon: <Brain className="h-4 w-4" />, color: '#7c3aed', ms: '~180ms' },
                              { name: 'Valkey Cache', icon: <Zap className="h-4 w-4" />, color: '#e67e00', ms: '<1ms' },
                              { name: 'AgentCore', icon: <Cpu className="h-4 w-4" />, color: '#1db954', ms: '~45ms' },
                            ].map((svc) => (
                              <div key={svc.name} className="rounded-xl px-4 py-3"
                                style={{ background: '#f5f5f7', border: '1px solid #ebebf0' }}
                              >
                                <div className="flex items-center gap-2 mb-2">
                                  <span style={{ color: svc.color }}>{svc.icon}</span>
                                  <span className="text-[13px] font-medium" style={{ color: '#1d1d1f' }}>{svc.name}</span>
                                </div>
                                <div className="flex items-center justify-between">
                                  <span className="text-[12px] tabular-nums font-medium" style={{ color: '#86868b' }}>{svc.ms}</span>
                                  <div className="flex items-center gap-1.5">
                                    <div className="w-2 h-2 rounded-full" style={{ background: '#1db954' }} />
                                    <span className="text-[12px] font-medium" style={{ color: '#1db954' }}>Healthy</span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Backend mode */}
                        <div className="rounded-2xl px-6 py-4 flex items-center justify-between" style={{
                          background: '#ffffff',
                          border: '1px solid #e5e5ea',
                        }}>
                          <div className="flex items-center gap-3">
                            <Server className="h-4 w-4" style={{ color: '#7c3aed' }} />
                            <span className="text-[15px] font-medium" style={{ color: '#1d1d1f' }}>Cache Backend</span>
                          </div>
                          <span className="text-[13px] px-3 py-1.5 rounded-full font-medium"
                            style={{
                              background: cacheStats?.mode === 'valkey' ? '#f0faf4' : '#fff8ee',
                              color: cacheStats?.mode === 'valkey' ? '#1db954' : '#e67e00',
                              border: `1px solid ${cacheStats?.mode === 'valkey' ? 'rgba(30,185,84,0.2)' : 'rgba(230,126,0,0.2)'}`,
                            }}
                          >
                            {cacheStats?.mode === 'valkey' ? 'ElastiCache' : cacheStats?.mode === 'memory' ? 'In-Memory' : '...'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                )}

                {/* Architecture Diagrams */}
                <div className="pt-6" style={{ borderTop: '1px solid #ebebf0' }}>
                  <div className="mb-6">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="w-8 h-[3px] rounded-full" style={{ background: '#d1d1d6' }} />
                      <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: '#86868b', letterSpacing: '0.1em' }}>
                        Reference
                      </span>
                    </div>
                    <h3 className="text-[28px] font-semibold tracking-tight" style={{ color: '#1d1d1f', letterSpacing: '-0.02em' }}>
                      Architecture Diagrams
                    </h3>
                    <p className="text-[16px] leading-[1.6] mt-2 max-w-[720px]" style={{ color: '#6e6e73' }}>
                      Reference diagrams showing the end-to-end system architecture at each stage of the workshop.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {archDiagrams.map((diagram, idx) => (
                      <motion.button
                        key={idx}
                        onClick={() => { onArchDiagram(diagram.img); onClose() }}
                        className="text-left p-5 rounded-2xl transition-all duration-200 flex items-center gap-3 group"
                        style={{
                          background: '#ffffff',
                          border: '1px solid #e5e5ea',
                        }}
                        whileHover={{
                          scale: 1.01,
                          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
                          borderColor: '#d1d1d6',
                        }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <Layers className="h-5 w-5 flex-shrink-0" style={{ color: '#86868b' }} />
                        <p className="text-[15px] font-medium" style={{ color: '#1d1d1f' }}>{diagram.title}</p>
                        <ArrowRight className="h-4 w-4 ml-auto opacity-0 group-hover:opacity-100 transition-all duration-200" style={{ color: '#86868b' }} />
                      </motion.button>
                    ))}
                  </div>
                </div>

                {/* Footer */}
                <div className="pt-6 pb-4 text-center">
                  <p className="text-[13px]" style={{ color: '#c7c7cc' }}>
                    Pellier Simulation Playground
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
