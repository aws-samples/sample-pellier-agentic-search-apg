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

/** The verified principal a turn ran as, from the server's `turn_start`. */
export interface TurnPrincipal {
  authenticated: boolean
  /** The customer the verified token maps to; null when signed out or staff. */
  customerId: string | null
  /** `workshop` when the shopper chooser's one-click sign-in set the session. */
  signInMethod: 'workshop' | 'cognito' | null
}

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
  /** How many places rerank moved the row, up positive; null without a fused rank. */
  moved: number | null
}

/** One excluded value and how many products it removed, with the noun to show ("4 candles"). */
export interface ExcludedCount {
  value: string
  count: number
  noun: string
}

export interface RankingFilters {
  kept: number
  of: number
  removed: Record<string, number>
  /** Each excluded value on its own, in the order the shopper named them. */
  excluded?: ExcludedCount[]
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

/**
 * One limit a catalog tool applied, as the page's tag. `origin` is where it
 * came from: `carried` reads "from earlier", `agent` (a limit the shopper
 * never stated) reads "added by Pellier"; null when the rail keeps no record
 * of the shopper's limits.
 */
export interface ResultLimit {
  kind: 'budget' | 'stock' | 'exclusions' | 'department' | string
  label: string
  value?: string
  origin: 'stated' | 'carried' | 'agent' | null
}

/**
 * The page grid's result for one search or browse: the tool's own order,
 * its size, its limits and its filter counts. Never computed in the browser.
 */
export interface StepResults {
  available: boolean
  rail?: string
  reason?: string
  product_ids?: string[]
  /** How many pieces the result holds: the count above the grid. */
  count?: number
  limits?: ResultLimit[]
  filters?: RankingFilters | null
  /** What this result cannot say, for the Builder view only. */
  note?: string
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
  /** The Aurora customer record the prompt carried, on the in-process Router step. */
  memory?: { facts: number; orders: number; source: string } | null
  /** The AgentCore Memory records whose preferences the prompt carried, on the Router step. */
  remembered?: { source: string; strategy: string; records: string[] } | null
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
  /** A search or browse's result for the page grid, on its done event. */
  results?: StepResults
}

/**
 * Merge a streamed step event into the list, by id. The backend gives each
 * tool use its own id, so two searches at once stay two steps; a call's
 * running and done events share one.
 */
export function upsertStep(steps: TurnStep[], incoming: TurnStep): TurnStep[] {
  const index = steps.findIndex(step => step.id === incoming.id)
  if (index < 0) return [...steps, incoming]
  const next = steps.slice()
  next[index] = { ...steps[index], ...incoming }
  return next
}
