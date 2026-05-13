/**
 * Agent Identity System — Single source of truth for agent colors, icons, and names.
 * Used across chat avatars, workflow visualizers, handoff diagrams, and product annotations.
 */

export type AgentType = 'search' | 'pricing' | 'recommendation' | 'orchestrator' | 'inventory' | 'support'

export interface AgentIdentity {
  name: string
  icon: string
  gradient: string
  bgColor: string
  borderColor: string
  textColor: string
  accentHex: string
}

export const AGENT_IDENTITIES: Record<AgentType, AgentIdentity> = {
  orchestrator: {
    name: 'Orchestrator',
    icon: 'O',
    gradient: 'linear-gradient(135deg, #a855f7 0%, #ec4899 100%)',
    bgColor: 'rgba(168, 85, 247, 0.1)',
    borderColor: 'rgba(168, 85, 247, 0.3)',
    textColor: 'text-purple-400',
    accentHex: '#a855f7',
  },
  support: {
    name: 'Support Agent',
    icon: 'H',
    gradient: 'linear-gradient(135deg, #14b8a6 0%, #0d9488 100%)',
    bgColor: 'rgba(20, 184, 166, 0.1)',
    borderColor: 'rgba(20, 184, 166, 0.3)',
    textColor: 'text-teal-400',
    accentHex: '#14b8a6',
  },
  search: {
    name: 'Search Agent',
    icon: 'S',
    gradient: 'linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%)',
    bgColor: 'rgba(59, 130, 246, 0.1)',
    borderColor: 'rgba(59, 130, 246, 0.3)',
    textColor: 'text-blue-400',
    accentHex: '#3b82f6',
  },
  inventory: {
    name: 'Inventory Agent',
    icon: 'I',
    gradient: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
    bgColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.3)',
    textColor: 'text-green-400',
    accentHex: '#10b981',
  },
  pricing: {
    name: 'Pricing Agent',
    icon: 'P',
    gradient: 'linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)',
    bgColor: 'rgba(245, 158, 11, 0.1)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
    textColor: 'text-amber-400',
    accentHex: '#f59e0b',
  },
  recommendation: {
    name: 'Recommendation Agent',
    icon: 'R',
    gradient: 'linear-gradient(135deg, #eab308 0%, #f97316 100%)',
    bgColor: 'rgba(234, 179, 8, 0.1)',
    borderColor: 'rgba(234, 179, 8, 0.3)',
    textColor: 'text-yellow-400',
    accentHex: '#eab308',
  },
}

export function resolveAgentType(agentName: string): AgentType {
  const lower = agentName.toLowerCase()
  if (lower.includes('support')) return 'support'
  if (lower.includes('search')) return 'search'
  if (lower.includes('inventory') || lower.includes('stock') || lower.includes('restock')) return 'inventory'
  if (lower.includes('pricing') || lower.includes('price')) return 'pricing'
  if (lower.includes('recommend')) return 'recommendation'
  return 'orchestrator'
}

export function getAgentIdentity(agentType: AgentType): AgentIdentity {
  return AGENT_IDENTITIES[agentType] || AGENT_IDENTITIES.orchestrator
}
