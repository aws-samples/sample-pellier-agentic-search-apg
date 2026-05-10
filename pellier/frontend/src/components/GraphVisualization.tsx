/**
 * GraphVisualization — Multi-agent DAG orchestrator visualization.
 * Shows the Router → [Agents] → Aggregator flow with animated edges.
 */
import { useState, useEffect } from 'react'
import { X, GitBranch, Cpu, CircleDot, Layers, Info } from 'lucide-react'

interface GraphVisualizationProps {
  isOpen: boolean
  onClose: () => void
}

interface GraphNode {
  id: string
  label: string
  type: 'decision' | 'agent' | 'aggregation'
  description: string
  model: string
}

interface GraphEdge {
  from: string
  to: string
  label: string
}

interface GraphData {
  available: boolean
  graph_builder_available: boolean
  nodes: GraphNode[]
  edges: GraphEdge[]
  description: string
}

const NODE_COLORS: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  decision: { bg: 'rgba(59, 130, 246, 0.08)', border: 'rgba(59, 130, 246, 0.25)', text: '#60a5fa', icon: '#60a5fa' },
  agent: { bg: 'rgba(52, 211, 153, 0.08)', border: 'rgba(52, 211, 153, 0.25)', text: '#34d399', icon: '#34d399' },
  aggregation: { bg: 'rgba(168, 85, 247, 0.08)', border: 'rgba(168, 85, 247, 0.25)', text: '#c084fc', icon: '#c084fc' },
}

const NodeIcon = ({ type }: { type: string }) => {
  const color = NODE_COLORS[type]?.icon || 'rgba(255,255,255,0.5)'
  if (type === 'decision') return <CircleDot className="h-5 w-5" style={{ color }} />
  if (type === 'aggregation') return <Layers className="h-5 w-5" style={{ color }} />
  return <Cpu className="h-5 w-5" style={{ color }} />
}

const GraphVisualization = ({ isOpen, onClose }: GraphVisualizationProps) => {
  const [data, setData] = useState<GraphData | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen && !data) {
      setLoading(true)
      fetch('/api/agents/graph')
        .then(r => r.json())
        .then(d => setData(d))
        .catch(() => setData({ available: false, graph_builder_available: false, nodes: [], edges: [], description: '' }))
        .finally(() => setLoading(false))
    }
  }, [isOpen])

  if (!isOpen) return null

  // Categorize nodes for layout
  const router = data?.nodes.find(n => n.type === 'decision')
  const agents = data?.nodes.filter(n => n.type === 'agent') || []
  const aggregator = data?.nodes.find(n => n.type === 'aggregation')

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[90vw] max-w-[900px] max-h-[85vh] rounded-[20px] flex flex-col overflow-hidden shadow-2xl"
        style={{ background: 'rgba(0, 0, 0, 0.95)', backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <div className="flex items-center gap-3">
            <GitBranch className="h-6 w-6" style={{ color: 'rgba(255, 255, 255, 0.6)' }} />
            <div>
              <h2 className="text-xl font-semibold" style={{ color: '#ffffff' }}>Graph Orchestrator</h2>
              <p className="text-xs mt-0.5" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                Multi-agent DAG — Strands 1.0 {data?.graph_builder_available ? '(GraphBuilder active)' : '(static structure)'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 transition-colors">
            <X className="h-5 w-5" style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6 search-scroll">
          {loading ? (
            <div className="text-center py-16">
              <GitBranch className="h-12 w-12 mx-auto mb-3 animate-pulse" style={{ color: 'rgba(255, 255, 255, 0.2)' }} />
              <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Loading graph structure...</p>
            </div>
          ) : data && data.available ? (
            <div className="space-y-8">
              {/* DAG Visualization — vertical flow */}
              <div className="flex flex-col items-center gap-2">
                {/* Router */}
                {router && (
                  <div
                    className="w-72 p-4 rounded-xl transition-all cursor-pointer"
                    style={{
                      background: hoveredNode === router.id ? 'rgba(59, 130, 246, 0.12)' : NODE_COLORS.decision.bg,
                      border: `1px solid ${NODE_COLORS.decision.border}`,
                    }}
                    onMouseEnter={() => setHoveredNode(router.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <NodeIcon type="decision" />
                      <span className="text-sm font-semibold" style={{ color: NODE_COLORS.decision.text }}>{router.label}</span>
                    </div>
                    <p className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{router.description}</p>
                    <p className="text-[9px] mt-1 font-mono" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>{router.model}</p>
                  </div>
                )}

                {/* Connector lines down */}
                <div className="flex items-center justify-center gap-0">
                  {agents.map((_, i) => (
                    <div key={i} className="flex flex-col items-center" style={{ width: 220 }}>
                      <div className="w-px h-8 animate-pulse" style={{ background: 'linear-gradient(to bottom, rgba(59, 130, 246, 0.4), rgba(52, 211, 153, 0.4))' }} />
                    </div>
                  ))}
                </div>

                {/* Agent nodes — horizontal */}
                <div className="flex gap-4 justify-center">
                  {agents.map(agent => {
                    const edge = data.edges.find(e => e.from === 'router' && e.to === agent.id)
                    return (
                      <div key={agent.id} className="flex flex-col items-center gap-1">
                        {edge && (
                          <span className="text-[9px] px-2 py-0.5 rounded-full mb-1" style={{ background: 'rgba(255, 255, 255, 0.04)', color: 'rgba(255, 255, 255, 0.35)' }}>
                            {edge.label}
                          </span>
                        )}
                        <div
                          className="w-52 p-4 rounded-xl transition-all cursor-pointer"
                          style={{
                            background: hoveredNode === agent.id ? 'rgba(52, 211, 153, 0.12)' : NODE_COLORS.agent.bg,
                            border: `1px solid ${NODE_COLORS.agent.border}`,
                          }}
                          onMouseEnter={() => setHoveredNode(agent.id)}
                          onMouseLeave={() => setHoveredNode(null)}
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <NodeIcon type="agent" />
                            <span className="text-xs font-semibold" style={{ color: NODE_COLORS.agent.text }}>{agent.label}</span>
                          </div>
                          <p className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{agent.description}</p>
                          <p className="text-[9px] mt-1 font-mono" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>{agent.model}</p>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Connector lines down */}
                <div className="flex items-center justify-center gap-0">
                  {agents.map((_, i) => (
                    <div key={i} className="flex flex-col items-center" style={{ width: 220 }}>
                      <div className="w-px h-8 animate-pulse" style={{ background: 'linear-gradient(to bottom, rgba(52, 211, 153, 0.4), rgba(168, 85, 247, 0.4))' }} />
                    </div>
                  ))}
                </div>

                {/* Aggregator */}
                {aggregator && (
                  <div
                    className="w-72 p-4 rounded-xl transition-all cursor-pointer"
                    style={{
                      background: hoveredNode === aggregator.id ? 'rgba(168, 85, 247, 0.12)' : NODE_COLORS.aggregation.bg,
                      border: `1px solid ${NODE_COLORS.aggregation.border}`,
                    }}
                    onMouseEnter={() => setHoveredNode(aggregator.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <NodeIcon type="aggregation" />
                      <span className="text-sm font-semibold" style={{ color: NODE_COLORS.aggregation.text }}>{aggregator.label}</span>
                    </div>
                    <p className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{aggregator.description}</p>
                    <p className="text-[9px] mt-1 font-mono" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>{aggregator.model}</p>
                  </div>
                )}
              </div>

              {/* Legend */}
              <div className="flex justify-center gap-6">
                {[
                  { type: 'decision', label: 'Decision Node' },
                  { type: 'agent', label: 'Specialist Agent' },
                  { type: 'aggregation', label: 'Aggregation' },
                ].map(item => (
                  <div key={item.type} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded" style={{ background: NODE_COLORS[item.type].border }} />
                    <span className="text-[10px]" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>{item.label}</span>
                  </div>
                ))}
              </div>

              {/* Description */}
              <div className="p-4 rounded-xl flex items-start gap-2" style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <Info className="h-4 w-4 mt-0.5 flex-shrink-0" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
                <p className="text-[11px] leading-relaxed" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{data.description}</p>
              </div>
            </div>
          ) : (
            <div className="text-center py-16">
              <GitBranch className="h-16 w-16 mx-auto mb-4" style={{ color: 'rgba(255, 255, 255, 0.1)' }} />
              <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Graph orchestrator unavailable</p>
              <p className="text-xs mt-1" style={{ color: 'rgba(255, 255, 255, 0.25)' }}>Requires Strands SDK with graph support</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3" style={{ borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
          <div className="flex items-center gap-2 text-xs" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
            <GitBranch className="h-3.5 w-3.5" style={{ color: 'rgba(255, 255, 255, 0.3)' }} />
            <span>
              <span className="font-medium" style={{ color: 'rgba(255, 255, 255, 0.6)' }}>Strands 1.0 Agents-as-Tools</span> — Router dispatches to specialist agents. Each agent has domain-specific tools registered via the Strands SDK.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default GraphVisualization
