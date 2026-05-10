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

// === CHALLENGE 9: Agent Identity — START ===
// TODO: Define AGENT_IDENTITIES record and resolveAgentType function
//
// Steps:
//   1. Create AGENT_IDENTITIES with entries for: orchestrator, support, search, inventory, pricing, recommendation
//   2. Each entry needs: name, icon, gradient, bgColor, borderColor, textColor, accentHex
//   3. Implement resolveAgentType(agentName) that maps agent name strings to AgentType
//   4. Priority order: support > search > inventory > pricing > recommendation > orchestrator (default)
//
// ⏩ SHORT ON TIME? Run:
//    cp solutions/module3/frontend/agentIdentity.ts pellier/frontend/src/utils/agentIdentity.ts

export const AGENT_IDENTITIES: Record<AgentType, AgentIdentity> = {
  orchestrator: { name: 'Orchestrator', icon: 'O', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#a855f7' },
  support: { name: 'Support Agent', icon: 'H', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#14b8a6' },
  search: { name: 'Style Advisor', icon: 'S', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#3b82f6' },
  inventory: { name: 'Stock Keeper', icon: 'I', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#10b981' },
  pricing: { name: 'Value Analyst', icon: 'P', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#f59e0b' },
  recommendation: { name: 'Curator', icon: 'R', gradient: '', bgColor: '', borderColor: '', textColor: '', accentHex: '#eab308' },
}

export function resolveAgentType(_agentName: string): AgentType {
  // TODO: Implement agent name resolution with priority ordering
  return 'orchestrator'
}
// === CHALLENGE 9: Agent Identity — END ===

export function getAgentIdentity(agentType: AgentType): AgentIdentity {
  return AGENT_IDENTITIES[agentType] || AGENT_IDENTITIES.orchestrator
}
