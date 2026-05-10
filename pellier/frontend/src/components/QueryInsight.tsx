import { Brain, DollarSign, Star, Tag, Zap, Database, Search, BarChart3 } from 'lucide-react'
import { extractPreferencesFromQuery } from '../utils/preferenceExtractor'
import { AGENT_IDENTITIES, type AgentType } from '../utils/agentIdentity'

interface QueryInsightProps {
  query: string
  agent?: 'search' | 'pricing' | 'recommendation' | 'orchestrator'
  phase?: 'thinking' | 'complete'
}

const QueryInsight = ({ query, agent, phase = 'complete' }: QueryInsightProps) => {
  const prefs = extractPreferencesFromQuery(query)

  const insights: Array<{icon: any, label: string, value: string, color: string}> = []

  if (prefs.budget) {
    insights.push({ icon: DollarSign, label: 'Budget', value: prefs.budget, color: 'text-green-400' })
  }
  if (prefs.quality) {
    insights.push({ icon: Star, label: 'Quality', value: prefs.quality, color: 'text-yellow-400' })
  }
  if (prefs.category) {
    insights.push({ icon: Tag, label: 'Category', value: prefs.category, color: 'text-purple-400' })
  }
  for (const feature of prefs.features) {
    insights.push({ icon: Zap, label: 'Feature', value: feature, color: 'text-blue-400' })
  }

  if (insights.length === 0 && phase === 'complete') return null

  const currentAgent = agent ? AGENT_IDENTITIES[agent as AgentType] : null

  const strategyLabel = prefs.searchStrategy === 'hybrid'
    ? 'Hybrid RRF 60/40'
    : prefs.searchStrategy === 'category'
      ? 'Category Filter'
      : 'Semantic Search'

  const pipelineSteps = [
    { icon: Database, label: 'Embedding', color: 'text-blue-400' },
    { icon: Search, label: 'Vector Search', color: 'text-purple-400' },
    { icon: BarChart3, label: 'Rank & Filter', color: 'text-green-400' },
  ]

  return (
    <div className="mb-3 p-3 rounded-xl bg-gradient-to-r from-purple-900/20 to-blue-900/20 border border-purple-500/30 backdrop-blur-sm animate-slideUp">
      <div className="flex items-center gap-2 mb-2">
        <Brain className="h-4 w-4 text-purple-400" />
        <span className="text-xs font-medium text-purple-300">
          {phase === 'thinking' ? 'Understanding Query...' : 'AI Understanding'}
        </span>
        {/* Search strategy chip */}
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/30 text-purple-300 font-medium">
          {strategyLabel}
        </span>
        {currentAgent && (
          <span className={`text-xs ${currentAgent.textColor} ml-auto`}>
            {currentAgent.icon} {currentAgent.name}
          </span>
        )}
      </div>

      {/* Search Pipeline Animation (thinking phase) */}
      {phase === 'thinking' && (
        <div className="flex items-center gap-1 mb-2.5">
          {pipelineSteps.map((step, idx) => {
            const StepIcon = step.icon
            return (
              <div key={idx} className="flex items-center">
                <div
                  className="flex items-center gap-1 px-2 py-1 rounded-lg bg-black/30 border border-white/10 pipeline-step"
                  style={{ animationDelay: `${idx * 0.5}s` }}
                >
                  <StepIcon className={`h-3 w-3 ${step.color}`} />
                  <span className={`text-[10px] font-medium ${step.color}`}>{step.label}</span>
                </div>
                {idx < pipelineSteps.length - 1 && (
                  <span className="text-purple-500/50 text-xs mx-0.5">→</span>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Insight chips */}
      {insights.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {insights.map((insight, idx) => {
            const Icon = insight.icon
            return (
              <div key={idx} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-black/30 border border-white/10">
                <Icon className={`h-3 w-3 ${insight.color}`} />
                <span className="text-xs text-gray-300">{insight.label}:</span>
                <span className={`text-xs font-medium ${insight.color}`}>{insight.value}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default QueryInsight
