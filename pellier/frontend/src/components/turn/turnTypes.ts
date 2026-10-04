/**
 * The step contract one agent turn streams, mirrored from
 * `services/turn_steps.py`. Shared by Ask Pellier and the Operator's
 * investigation graph.
 */

export type StepStatus = 'running' | 'done' | 'failed'

export type TurnState = 'working' | 'done' | 'failed'

export interface TurnStatus {
  label: string
  state: TurnState
}

export type BindingVerdict = 'overwritten' | 'matched' | 'bound' | 'refused' | 'unbound'

/** Who chose a call's customer, from the binding code itself. */
export interface IdentityBinding {
  binding: BindingVerdict
  requested_customer: string | null
  bound_customer: string | null
  authorized_customer: string | null
}

export interface RankingRow {
  product_id: string
  name: string | null
  fts_rank: number | null
  vec_rank: number | null
  similarity: number | null
  rrf_score: number | null
  rerank_score: number | null
  before: number | null
  after: number
}

export interface RankingFilters {
  kept: number
  of: number
  removed: Record<string, number>
}

export interface RankingPayload {
  available: boolean
  rail?: string
  reason?: string
  method?: string | null
  rrf_k?: number
  rerank_pool?: number | null
  arms?: { full_text: number; vector: number; fused: number }
  filters?: RankingFilters | null
  rows?: RankingRow[]
  note?: string
  receipt_id?: number | null
}

/** The limits a catalog tool applied, as the shopper would say them. */
export interface StepRequirements {
  applied: string[]
  /** The limits kept from earlier in the conversation. */
  carried: string[]
}

export interface LoadedSkill {
  name: string
  display_name: string
  path: string
  loaded: 'fixed' | 'on demand'
}

export interface StepBuilder {
  tool: string | null
  rail?: string
  duration_ms?: number | null
  audit_id?: number | null
  receipt_id?: number | null
  identity?: IdentityBinding | null
  ranking?: RankingPayload | null
  requirements?: StepRequirements | null
  intent?: string
  agent?: string
  model_id?: string
  skills?: LoadedSkill[]
  skill_mode?: string
  memory?: { facts: number; orders: number; source: string } | null
  note?: string | null
  /** How the agent's turn ended (`end_turn`, `max_tokens`, ...), on the Router step once known. */
  stop_reason?: string | null
}

export interface TurnStep {
  id: string
  label: string
  status: StepStatus
  finding?: string
  tags: string[]
  builder?: StepBuilder
}

/** Merge a streamed step event into the list, by id. */
export function upsertStep(steps: TurnStep[], incoming: TurnStep): TurnStep[] {
  const index = steps.findIndex(step => step.id === incoming.id)
  if (index < 0) return [...steps, incoming]
  const next = steps.slice()
  next[index] = { ...steps[index], ...incoming }
  return next
}
