/**
 * Agent Identity System — Single source of truth for agent colors, icons, and names.
 * Used across chat avatars, workflow visualizers, handoff diagrams, and product annotations.
 */

export type AgentType = 'router' | 'shopping' | 'stock' | 'support'

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
  router: {
    name: 'Router',
    icon: 'R',
    gradient: 'linear-gradient(135deg, #a855f7 0%, #ec4899 100%)',
    bgColor: 'rgba(168, 85, 247, 0.1)',
    borderColor: 'rgba(168, 85, 247, 0.3)',
    textColor: 'text-purple-400',
    accentHex: '#a855f7',
  },
  shopping: {
    name: 'Shopping agent',
    icon: 'S',
    gradient: 'linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%)',
    bgColor: 'rgba(59, 130, 246, 0.1)',
    borderColor: 'rgba(59, 130, 246, 0.3)',
    textColor: 'text-blue-400',
    accentHex: '#3b82f6',
  },
  stock: {
    name: 'Stock agent',
    icon: 'K',
    gradient: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
    bgColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.3)',
    textColor: 'text-green-400',
    accentHex: '#10b981',
  },
  support: {
    name: 'Support agent',
    icon: 'H',
    gradient: 'linear-gradient(135deg, #14b8a6 0%, #0d9488 100%)',
    bgColor: 'rgba(20, 184, 166, 0.1)',
    borderColor: 'rgba(20, 184, 166, 0.3)',
    textColor: 'text-teal-400',
    accentHex: '#14b8a6',
  },
}

export function resolveAgentType(agentName: string): AgentType {
  const lower = agentName.toLowerCase()
  if (lower.includes('support')) return 'support'
  if (lower.includes('stock')) return 'stock'
  if (lower.includes('shopping')) return 'shopping'
  return 'router'
}

export function getAgentIdentity(agentType: AgentType): AgentIdentity {
  return AGENT_IDENTITIES[agentType] || AGENT_IDENTITIES.router
}
