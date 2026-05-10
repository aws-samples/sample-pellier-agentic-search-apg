/**
 * Agent Handoff Visualizer — Horizontal pipeline showing agent routing flow.
 * Displays [Orchestrator] → [Specialist] → [Tool] with animated connections.
 */
import { AGENT_IDENTITIES, resolveAgentType } from '../utils/agentIdentity'

interface AgentStep {
  agent: string
  action: string
  status: string
  timestamp: number
  duration_ms: number
}

interface ToolCall {
  tool: string
  params?: string
  timestamp: number
  duration_ms: number
  status: string
}

interface RoutingDecision {
  selected_agent: string
  confidence: number
  reason: string
  alternatives: Array<{ agent: string; confidence: number }>
}

interface AgentExecution {
  agent_steps: AgentStep[]
  tool_calls: ToolCall[]
  routing_decision?: RoutingDecision
  total_duration_ms: number
}

interface AgentHandoffVisualizerProps {
  execution: AgentExecution
  isActive: boolean
}

const AgentHandoffVisualizer = ({ execution, isActive }: AgentHandoffVisualizerProps) => {
  if (!execution || execution.agent_steps.length === 0) return null

  // Deduplicate agents to build the pipeline nodes
  const seenAgents = new Set<string>()
  const pipelineNodes: Array<{ agent: string; duration_ms: number; status: string }> = []
  for (const step of execution.agent_steps) {
    const key = step.agent
    if (!seenAgents.has(key)) {
      seenAgents.add(key)
      pipelineNodes.push({ agent: step.agent, duration_ms: step.duration_ms, status: step.status })
    }
  }

  // Add tool call node if there are tool calls
  const hasTools = execution.tool_calls.length > 0
  const toolName = hasTools ? execution.tool_calls[0].tool : null
  const toolDuration = hasTools ? execution.tool_calls.reduce((sum, t) => sum + t.duration_ms, 0) : 0

  return (
    <div className="mb-2 p-2.5 rounded-lg animate-slideUp" style={{
      background: 'rgba(106, 27, 154, 0.04)',
      border: '1px solid rgba(186, 104, 200, 0.15)',
    }}>
      <div className="flex items-center gap-1 overflow-x-auto">
        {pipelineNodes.map((node, idx) => {
          const agentType = resolveAgentType(node.agent)
          const identity = AGENT_IDENTITIES[agentType]
          const isNodeActive = isActive && idx === pipelineNodes.length - 1

          return (
            <div key={idx} className="flex items-center">
              {/* Node */}
              <div className="flex flex-col items-center gap-0.5">
                <div
                  className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-semibold text-white whitespace-nowrap ${isNodeActive ? 'animate-pulse' : ''}`}
                  style={{ background: identity.gradient, boxShadow: isNodeActive ? `0 0 12px ${identity.accentHex}40` : undefined }}
                >
                  <span>{identity.icon}</span>
                  <span>{identity.name}</span>
                </div>
                <span className="text-[9px] text-gray-500">
                  {node.duration_ms > 0 ? `${node.duration_ms}ms` : isNodeActive ? '...' : ''}
                </span>
              </div>

              {/* Connector arrow */}
              {(idx < pipelineNodes.length - 1 || hasTools) && (
                <div className="flex flex-col items-center mx-1">
                  <svg width="24" height="12" viewBox="0 0 24 12" className="text-purple-500/40">
                    <line x1="0" y1="6" x2="18" y2="6" stroke="currentColor" strokeWidth="1.5"
                      strokeDasharray="4 3"
                      className={isActive ? 'animate-dash-flow' : ''}
                      style={{ strokeDashoffset: 0 }}
                    />
                    <polygon points="18,2 24,6 18,10" fill="currentColor" />
                  </svg>
                  {/* Confidence label on first arrow */}
                  {idx === 0 && execution.routing_decision && (
                    <span className="text-[8px] text-purple-400 -mt-0.5">
                      {execution.routing_decision.confidence}%
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* Tool node */}
        {hasTools && (
          <div className="flex flex-col items-center gap-0.5">
            <div
              className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-semibold text-white whitespace-nowrap ${isActive ? 'animate-pulse' : ''}`}
              style={{
                background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                boxShadow: isActive ? '0 0 12px rgba(34, 197, 94, 0.4)' : undefined,
              }}
            >
              <span style={{ fontSize: '10px' }}>T</span>
              <span className="font-mono max-w-[80px] truncate">{toolName}</span>
            </div>
            <span className="text-[9px] text-gray-500">
              {toolDuration > 0 ? `${toolDuration}ms` : isActive ? '...' : ''}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default AgentHandoffVisualizer
