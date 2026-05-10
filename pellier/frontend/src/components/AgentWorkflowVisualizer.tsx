/**
 * Agent Workflow Visualizer - Real-time agent orchestration display
 */
import { useEffect, useState } from 'react'
import { useTheme } from '../App'
import { resolveAgentType, AGENT_IDENTITIES } from '../utils/agentIdentity'

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
  result?: string
  timestamp: number
  duration_ms: number
  status: string
}

interface RoutingDecision {
  selected_agent: string
  confidence: number
  reason: string
  alternatives: Array<{agent: string, confidence: number}>
}

interface AgentExecution {
  agent_steps: AgentStep[]
  tool_calls: ToolCall[]
  reasoning_steps: Array<{step: string, content: string, timestamp: number}>
  routing_decision?: RoutingDecision
  total_duration_ms: number
  success_rate: number
}

interface Props {
  execution: AgentExecution | null
  isActive: boolean
}

const AgentWorkflowVisualizer = ({ execution, isActive }: Props) => {
  const { theme } = useTheme()
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    if (isActive && execution) {
      let step = 0
      const interval = setInterval(() => {
        step++
        setActiveStep(step)
        if (step >= execution.agent_steps.length) {
          clearInterval(interval)
        }
      }, 300)
      return () => clearInterval(interval)
    } else {
      setActiveStep(execution?.agent_steps.length || 0)
    }
  }, [isActive, execution])

  if (!execution) return null

  const getAgentIcon = (agent: string) => {
    return AGENT_IDENTITIES[resolveAgentType(agent)]?.icon || 'AI'
  }

  return (
    <div className="mb-4 p-4 rounded-xl" style={{
      background: theme === 'dark' 
        ? 'rgba(106, 27, 154, 0.05)' 
        : 'rgba(106, 27, 154, 0.03)',
      border: '1px solid rgba(186, 104, 200, 0.2)'
    }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-text-primary">Agent Workflow</span>
          <span className="text-[10px] text-text-secondary">
            {execution.total_duration_ms}ms
          </span>
        </div>
        <div className="text-[10px] text-green-400">
          ✓ {execution.success_rate}% Success
        </div>
      </div>

      {/* Routing Decision */}
      {execution.routing_decision && (
        <div className="mb-3 p-2.5 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
          <div className="text-[10px] font-semibold text-purple-300 mb-1.5">Agent Routing Decision</div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-text-primary">{execution.routing_decision.selected_agent}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-semibold">
              {execution.routing_decision.confidence}% confidence
            </span>
          </div>
          <div className="text-[10px] text-text-secondary mb-1">{execution.routing_decision.reason}</div>
          {execution.routing_decision.alternatives.length > 0 && (
            <div className="text-[10px] text-text-secondary">
              Alternative: {execution.routing_decision.alternatives[0].agent} ({execution.routing_decision.alternatives[0].confidence}%)
            </div>
          )}
        </div>
      )}

      {/* Agent Steps */}
      <div className="space-y-1.5">
        {execution.agent_steps.map((step, idx) => (
          <div
            key={idx}
            className={`flex items-center gap-2 p-1.5 rounded-lg transition-all duration-300 ${
              idx < activeStep ? 'opacity-100' : 'opacity-40'
            }`}
            style={{
              background: idx < activeStep 
                ? 'rgba(106, 27, 154, 0.1)' 
                : 'rgba(255, 255, 255, 0.02)',
              transform: idx < activeStep ? 'translateX(0)' : 'translateX(-10px)'
            }}
          >
            {/* Agent Icon */}
            <div className="text-lg">{getAgentIcon(step.agent)}</div>
            
            {/* Agent Info */}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-text-primary">{step.agent}</div>
              <div className="text-[10px] text-text-secondary truncate">{step.action}</div>
            </div>

            {/* Duration */}
            <div className="text-[10px] text-purple-400">{step.duration_ms}ms</div>

            {/* Status */}
            {step.status === 'completed' && (
              <div className="text-green-400 text-sm">✓</div>
            )}
            {step.status === 'in_progress' && (
              <div className="animate-spin text-purple-400">⏳</div>
            )}
            {idx < activeStep && step.status !== 'completed' && step.status !== 'in_progress' && (
              <div className="text-green-400 text-sm">✓</div>
            )}
            {idx === activeStep && isActive && step.status !== 'in_progress' && (
              <div className="animate-spin text-purple-400">⏳</div>
            )}
          </div>
        ))}
      </div>

      {/* Tool Calls Timeline - Now streams in real-time */}
      {execution.tool_calls.length > 0 && (
        <div className="mt-3 pt-2 border-t border-purple-500/20">
          <div className="text-[10px] font-semibold text-text-secondary mb-2">
            Tool Calls {isActive && <span className="text-purple-400 animate-pulse">(Live)</span>}
          </div>
          <div className="space-y-2">
            {execution.tool_calls.map((tool, idx) => {
              const isExecuting = isActive && (tool.status === 'executing' || tool.status === 'in_progress')
              return (
                <div
                  key={idx}
                  className="p-2 rounded-lg animate-slideUp"
                  style={{
                    background: isExecuting ? 'rgba(139, 92, 246, 0.08)' : 'rgba(34, 197, 94, 0.05)',
                    border: isExecuting ? '1px solid rgba(139, 92, 246, 0.4)' : '1px solid rgba(34, 197, 94, 0.2)',
                    animation: isExecuting ? 'pipelineStep 1.5s ease-in-out infinite' : undefined,
                  }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {isExecuting ? (
                      <span className="animate-spin text-purple-400 text-xs">⏳</span>
                    ) : (
                      <span className="text-green-400 text-xs">✓</span>
                    )}
                    <span className="text-text-primary font-mono text-xs font-semibold">{tool.tool}()</span>
                    <span className="ml-auto text-purple-400 text-[10px]">
                      {tool.duration_ms > 0 ? `${tool.duration_ms}ms` : isExecuting ? 'running...' : ''}
                    </span>
                  </div>
                  {tool.params && (
                    <div className="text-[10px] text-text-secondary ml-5 mb-0.5 font-mono">
                      {tool.params}
                    </div>
                  )}
                  {tool.result && (
                    <div className="text-[10px] text-green-400 ml-5">
                      → {tool.result}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Reasoning Steps */}
      {execution.reasoning_steps.length > 0 && (
        <div className="mt-2 pt-2 border-t border-purple-500/20">
          <div className="text-[10px] font-semibold text-text-secondary mb-1.5">
            Claude 4 Reasoning
          </div>
          {execution.reasoning_steps.map((reasoning, idx) => (
            <div
              key={idx}
              className="text-[10px] p-1.5 rounded mb-1"
              style={{ background: 'rgba(186, 104, 200, 0.05)' }}
            >
              <div className="font-semibold text-purple-400 mb-0.5">{reasoning.step}</div>
              <div className="text-text-secondary italic">{reasoning.content}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default AgentWorkflowVisualizer
