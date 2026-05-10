/**
 * ModuleCompletionModal — Celebratory summary shown when a module is detected
 * as newly completed by the /api/workshop/status endpoint.
 */
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, X, Zap, Network, Server } from 'lucide-react'

type ModuleKey = 'module1' | 'module2' | 'module3'

interface Capability {
  icon: string
  label: string
  detail: string
}

interface ModuleInfo {
  title: string
  headline: string
  subhead: string
  capabilities: Capability[]
  techDetail: string
  accentColor: string
  Icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>
}

const MODULE_INFO: Record<ModuleKey, ModuleInfo> = {
  module1: {
    title: 'Module 1 Complete',
    headline: 'Your database now understands meaning.',
    subhead: 'You implemented pgvector semantic search on Amazon Aurora PostgreSQL.',
    capabilities: [
      { icon: '\u{1f50d}', label: 'Semantic search live', detail: '"Budget laptop for college" now finds relevant results' },
      { icon: '\u26a1', label: 'HNSW index active', detail: 'Sub-10ms vector queries via pgvector 0.8.0 HNSW' },
      { icon: '\u{1f500}', label: 'Hybrid RRF fusion', detail: 'Vector + full-text results merged via Reciprocal Rank Fusion' },
    ],
    techDetail: 'Cohere Embed v4 (1024-dim) + pgvector cosine distance (<=> operator) + HNSW ef_search=40',
    accentColor: '#3b82f6',
    Icon: Zap,
  },
  module2: {
    title: 'Module 2 Complete',
    headline: 'A multi-agent team is live in the storefront.',
    subhead: 'You built @tool functions, specialist agents, and a multi-agent orchestrator.',
    capabilities: [
      { icon: '\u{1f6e0}\ufe0f', label: 'Agent tools active', detail: 'get_whats_trending and other @tool functions query Aurora on demand' },
      { icon: '\u{1f3af}', label: 'Orchestrator routing live', detail: 'Queries routed to the right specialist automatically' },
      { icon: '\u{1f91d}', label: 'Agent-as-tool pattern', detail: '5 specialist agents collaborate: search, pricing, inventory, recommendation, support' },
    ],
    techDetail: 'Strands SDK @tool + agent-as-tool pattern + orchestrator (Claude Haiku 4.5) + 5 specialists (Opus 4.6)',
    accentColor: '#7c3aed',
    Icon: Network,
  },
  module3: {
    title: 'Module 3 Complete',
    headline: 'Production-grade infrastructure is live.',
    subhead: 'You connected AgentCore Memory, MCP Gateway, and Cedar policy evaluation.',
    capabilities: [
      { icon: '\u{1f9e0}', label: 'AgentCore Memory active', detail: 'User preferences persist across sessions automatically' },
      { icon: '\u{1f50c}', label: 'MCP Gateway connected', detail: 'Tools discovered dynamically via Model Context Protocol' },
      { icon: '\u{1f6e1}\ufe0f', label: 'Cedar policies enforced', detail: 'Agent actions evaluated against fine-grained authorization rules' },
    ],
    techDetail: 'AgentCore Memory (session manager) + AgentCore Gateway (MCP/HTTP) + Cedar policy engine',
    accentColor: '#10b981',
    Icon: Server,
  },
}

interface ModuleCompletionModalProps {
  moduleKeys: string[]
  onClose: () => void
}

const ModuleCompletionModal = ({ moduleKeys, onClose }: ModuleCompletionModalProps) => {
  const key = moduleKeys[0] as ModuleKey
  if (!key || !MODULE_INFO[key]) return null
  const info = MODULE_INFO[key]
  const { Icon } = info

  return (
    <AnimatePresence>
      <div
        className="fixed inset-0 z-[1100] flex items-center justify-center"
        style={{ background: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(4px)' }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.92, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: 20 }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
          style={{
            width: '90vw',
            maxWidth: 520,
            borderRadius: 20,
            overflow: 'hidden',
            background: 'rgba(10, 10, 10, 0.96)',
            border: `1px solid ${info.accentColor}33`,
            backdropFilter: 'blur(40px)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '24px 24px 16px',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ padding: 10, borderRadius: 12, background: `${info.accentColor}22` }}>
                <Icon className="h-5 w-5" style={{ color: info.accentColor }} />
              </div>
              <div>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                    color: info.accentColor,
                    marginBottom: 2,
                  }}
                >
                  {info.title}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CheckCircle className="h-4 w-4" style={{ color: '#34d399' }} />
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#ffffff' }}>Stub implemented</span>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                padding: 6,
                borderRadius: 8,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <X className="h-4 w-4" style={{ color: 'rgba(255,255,255,0.4)' }} />
            </button>
          </div>

          {/* Body */}
          <div style={{ padding: '20px 24px' }}>
            <h3 style={{ fontSize: 18, fontWeight: 600, color: '#ffffff', margin: '0 0 4px' }}>{info.headline}</h3>
            <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)', margin: '0 0 20px' }}>{info.subhead}</p>

            {/* Capabilities */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
              {info.capabilities.map((cap) => (
                <div
                  key={cap.label}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 12,
                    padding: 12,
                    borderRadius: 12,
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}
                >
                  <span style={{ fontSize: 16, flexShrink: 0, marginTop: 2 }}>{cap.icon}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#ffffff', marginBottom: 2 }}>
                      {cap.label}
                    </div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>{cap.detail}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Tech detail */}
            <div
              style={{
                fontSize: 11,
                padding: '8px 12px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.04)',
                color: 'rgba(255,255,255,0.35)',
                fontFamily: 'monospace',
              }}
            >
              {info.techDetail}
            </div>
          </div>

          {/* Footer */}
          <div style={{ padding: '0 24px 20px' }}>
            <button
              onClick={onClose}
              style={{
                width: '100%',
                padding: '10px 0',
                borderRadius: 12,
                fontSize: 14,
                fontWeight: 600,
                background: info.accentColor,
                color: '#ffffff',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Continue building
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}

export default ModuleCompletionModal
