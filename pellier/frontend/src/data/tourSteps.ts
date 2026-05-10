import type { WorkshopMode } from '../contexts/LayoutContext'

export type TooltipPosition = 'top' | 'bottom' | 'left' | 'right'

export interface TourAction {
  label: string
  actionKey: 'focus-search' | 'open-sql-inspector' | 'open-hybrid-search' |
    'open-agent-traces' | 'open-context-dashboard' | 'open-chat' |
    'open-guardrails' | 'toggle-chaos' | 'open-dev-tools'
}

export interface TourStep {
  selector: string
  title: string
  description: string
  position: TooltipPosition
  tryItAction?: TourAction
  spotlightPadding?: number
  celebration?: boolean
}

export const TOUR_STEPS: Record<WorkshopMode, TourStep[]> = {
  // ─────────────────────────────────────────────────────────────
  // LEGACY — Emphasize limitations. This is the "before" state.
  // ─────────────────────────────────────────────────────────────
  legacy: [
    {
      selector: '[data-tour="hero-badge"]',
      title: 'Before any AI',
      description: 'Pellier as it started — a plain SQL storefront that only finds what you literally type.',
      position: 'bottom',
    },
    {
      selector: '[data-tour="hero-search"]',
      title: 'Keywords, nothing more',
      description: 'Search "MacBook Air" and it lands. Search "something to keep my drinks cold" and it shrugs. Try both.',
      position: 'bottom',
      tryItAction: { label: 'Try it', actionKey: 'focus-search' },
      spotlightPadding: 12,
    },
    {
      selector: '[data-tour="workshop-pills"]',
      title: 'What\'s missing',
      description: 'No meaning, no chat, no agents. This is where every real storefront starts. Pick Smart Search to begin.',
      position: 'bottom',
    },
  ],

  // ─────────────────────────────────────────────────────────────
  // SMART SEARCH — The first upgrade. Search understands meaning.
  // ─────────────────────────────────────────────────────────────
  search: [
    {
      selector: '[data-tour="hero-badge"]',
      title: 'Search, re-made',
      description: 'Every product is now a 1024-dim Cohere embedding in pgvector. Meaning, not spelling.',
      position: 'bottom',
    },
    {
      selector: '[data-tour="hero-search"]',
      title: 'Ask in your own words',
      description: 'Try "something to keep my drinks cold" — insulated bottles and tumblers, no product names required.',
      position: 'bottom',
      tryItAction: { label: 'Try it', actionKey: 'focus-search' },
      spotlightPadding: 12,
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'See the query',
      description: 'Inspect the live pgvector SQL — cosine distance, HNSW index, business filters layered on top.',
      position: 'right',
      tryItAction: { label: 'Open Dev Tools', actionKey: 'open-dev-tools' },
      spotlightPadding: 10,
    },
    {
      selector: '[data-tour="workshop-pills"]',
      title: 'Now teach it to talk',
      description: 'Semantic search is live. Pick Agentic AI to wrap it in tools, specialists, and an orchestrator.',
      position: 'bottom',
    },
  ],

  // ─────────────────────────────────────────────────────────────
  // AGENTIC AI — Tools, agents, and orchestration.
  // ─────────────────────────────────────────────────────────────
  agentic: [
    {
      selector: '[data-tour="chat-bubble"]',
      title: 'Talk to Pellier',
      description: 'Your search functions are now @tool-decorated. An agent discovers them and picks what to call.',
      position: 'top',
      tryItAction: { label: 'Open chat', actionKey: 'open-chat' },
      spotlightPadding: 16,
    },
    {
      selector: '[data-tour="chat-bubble"]',
      title: 'Five specialists, one voice',
      description: 'Search, Recommendation, Pricing, Inventory, Support. Ask something that crosses domains and watch the routing.',
      position: 'top',
      tryItAction: { label: 'Open chat', actionKey: 'open-chat' },
      spotlightPadding: 16,
    },
    {
      selector: '[data-tour="search-bar"]',
      title: 'Search moves up',
      description: 'With chat active, the search bar retreats to the header. The camera icon does visual search — drop a photo, find the piece.',
      position: 'bottom',
      spotlightPadding: 12,
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'Watch the agent think',
      description: 'Every tool call is traced — inputs, outputs, latency, token cost. The whole reasoning chain, on display.',
      position: 'right',
      tryItAction: { label: 'Open traces', actionKey: 'open-agent-traces' },
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'Guardrails & chaos',
      description: 'Bedrock Guardrails filter the bad stuff. Chaos Mode injects failures so your retry paths earn their keep.',
      position: 'right',
      tryItAction: { label: 'Open Guardrails', actionKey: 'open-guardrails' },
    },
    {
      selector: '[data-tour="workshop-pills"]',
      title: 'Local is done',
      description: 'Semantic search, tools, orchestration — all running on your machine. Pick Production for AgentCore.',
      position: 'bottom',
    },
  ],

  // ─────────────────────────────────────────────────────────────
  // PRODUCTION — AgentCore infrastructure for enterprise deployment.
  // ─────────────────────────────────────────────────────────────
  production: [
    {
      selector: '[data-tour="hero-badge"]',
      title: 'Same agents, real infrastructure',
      description: 'Cognito for identity, AgentCore Memory for preferences, MCP Gateway for tools, Cedar for who-can-call-what.',
      position: 'bottom',
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'Memory that lasts',
      description: 'AgentCore Memory retires your local session store. Say "I prefer Nike" once; the next visit remembers.',
      position: 'right',
      tryItAction: { label: 'Open Dev Tools', actionKey: 'open-dev-tools' },
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'Every hop, traced',
      description: 'OpenTelemetry captures Orchestrator → Specialist → Tool → Aurora with latency and cost on every edge.',
      position: 'right',
      tryItAction: { label: 'Open Dev Tools', actionKey: 'open-dev-tools' },
    },
    {
      selector: '[data-tour="dev-tools-tab"]',
      title: 'Policies that hold',
      description: 'Try restocking 1,000 units — Cedar blocks it before the agent runs. Authored in natural language, enforced at the edge.',
      position: 'right',
      tryItAction: { label: 'Open Dev Tools', actionKey: 'open-dev-tools' },
    },
    {
      selector: '[data-tour="hero-badge"]',
      title: 'You shipped it.',
      description: 'Semantic search on Aurora, Strands-powered agents, managed memory, traced end-to-end, policy-gated.',
      position: 'bottom',
      celebration: true,
    },
  ],
}
