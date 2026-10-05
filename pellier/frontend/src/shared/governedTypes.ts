/**
 * Shared governed status vocabulary for Pellier and Observatory.
 *
 * These types deliberately mirror what the backend already emits. Nothing
 * here is invented:
 *
 *   - `ExecutionRail` matches `services/execution_rail.py`
 *     (`in-process` | `runtime` | `gateway-mcp`).
 *   - `EvidenceProvenance` matches the four words the backend uses on the
 *     evaluations envelope and the managed-runtime receipt
 *     (`live` | `fixture` | `modeled` | `unavailable`).
 *   - `PolicyDecision` matches the Cedar outcomes the audit surfaces
 *     already render.
 *
 * The reason this file exists rather than each surface declaring its own
 * union: when Pellier and Observatory disagree about what "governed" means,
 * an attendee cannot trust either. One vocabulary, two presentations.
 *
 * Deliberate omission: there is no `turnId` here. Deriving one from array
 * position would produce deep links that silently point at the wrong turn
 * after a refresh; the turn id travels on the chat response instead.
 */

/**
 * Execution rail as reported by the backend on a completed turn.
 *
 * `refused` is not a rail the work ran on: it records that the governed rail
 * was required, was unavailable, and the call was declined rather than
 * quietly served in-process.
 */
export type ExecutionRail =
  | 'in-process'
  | 'runtime'
  | 'gateway-mcp'
  | 'refused'

/**
 * Policy outcome.
 *
 * Six states, and the distinctions are the point:
 *
 *   ALLOW                 the engine permitted the action
 *   DENY                  the engine blocked it before execution
 *   WOULD_DENY            a real deny event under LOG_ONLY: observed, not enforced
 *   NOT_EVALUATED         no engine was asked
 *   EVALUATION_INCOMPLETE an engine was asked and the answer could not be read
 *   POLICY_INFERRED       a text scan of policy source, which is not a decision
 *
 * `EVALUATION_INCOMPLETE` and `POLICY_INFERRED` exist because their absence
 * pushed both cases into NOT_EVALUATED, where "we could not read the decision
 * log" was indistinguishable from "no policy engine is involved".
 */
export type PolicyDecision =
  | 'ALLOW'
  | 'DENY'
  | 'WOULD_DENY'
  | 'NOT_EVALUATED'
  | 'EVALUATION_INCOMPLETE'
  | 'POLICY_INFERRED'

/**
 * Where a displayed value came from. Shared with the backend so a number
 * cannot change meaning as it crosses the wire.
 *
 * `live`        measured on this request
 * `fixture`     illustrative; describes no run
 * `modeled`     calculated, not observed
 * `unavailable` not provisioned
 */
export type EvidenceProvenance = 'live' | 'fixture' | 'modeled' | 'unavailable'

/**
 * The rail decision the backend attaches to a completed turn.
 *
 * Mirrors `RailDecision.to_dict()` in `services/execution_rail.py`.
 * `available: false` with `managedRequested: true` is the degraded case:
 * the governed rail was asked for and could not serve the request.
 */
export interface RailDecision {
  rail: ExecutionRail
  managedRequested: boolean
  available: boolean
  reason: string | null
}

/** Disclosure attached to a turn that ran on a rail it did not intend to. */
export interface RailDegradation {
  degraded: boolean
  reason: string | null
  rail: ExecutionRail
  capabilitiesRemoved: string[]
  explanation: string
}

/**
 * Whether the governed rail was actually verified for a turn.
 *
 * `verified` is reserved for a confirmed `gateway-mcp` rail. A turn that
 * merely selected the managed runtime is `selected`, not verified — the
 * entrypoint confirms Gateway itself, and claiming otherwise would put a
 * green seal on an unproven path.
 */
export type GovernedRailState =
  | 'verified'
  | 'selected'
  | 'in-process'
  | 'degraded'
  | 'refused'
  | 'unknown'

/**
 * Resolve the seal state from a rail decision.
 *
 * @param decision The backend's rail decision, when present.
 * @returns The state a seal may display. Absent evidence resolves to
 *   `unknown` rather than to a positive claim.
 */
export function resolveRailState(
  decision?: RailDecision | null,
): GovernedRailState {
  if (!decision) return 'unknown'
  // A refusal outranks degradation: nothing ran at all.
  if (decision.rail === 'refused') return 'refused'
  if (decision.managedRequested && !decision.available) return 'degraded'
  if (decision.rail === 'gateway-mcp') return 'verified'
  if (decision.rail === 'runtime') return 'selected'
  if (decision.rail === 'in-process') return 'in-process'
  return 'unknown'
}

/** Human-readable label per rail state. Paired with an icon, never alone. */
export const RAIL_STATE_LABEL: Record<GovernedRailState, string> = {
  verified: 'Governed',
  selected: 'Managed runtime',
  'in-process': 'In-process',
  degraded: 'Degraded',
  refused: 'Refused',
  unknown: 'Rail unknown',
}

/** One-line explanation of each rail state, for tooltips and disclosure. */
export const RAIL_STATE_DETAIL: Record<GovernedRailState, string> = {
  verified:
    'Tools ran over the AgentCore Gateway MCP rail under the caller’s identity.',
  selected:
    'The managed runtime was selected; the Gateway rail is not yet confirmed for this turn.',
  'in-process':
    'Tools ran in this process against Aurora directly. A legitimate rail, not a failure.',
  degraded:
    'The governed rail was requested but unavailable, so mutation-capable tools were withheld. This is not a policy denial.',
  refused: 'Refused: governed rail unavailable',
  unknown: 'No rail was reported for this turn.',
}

/** Provenance label text. Kept identical to the backend's wording. */
export const PROVENANCE_LABEL: Record<EvidenceProvenance, string> = {
  live: 'Live',
  fixture: 'Fixture',
  modeled: 'Modeled',
  unavailable: 'Unavailable',
}

/** What each provenance value actually claims about a number. */
export const PROVENANCE_DETAIL: Record<EvidenceProvenance, string> = {
  live: 'measured on this request',
  fixture: 'illustrative — describes no run',
  modeled: 'calculated, not observed',
  unavailable: 'not provisioned',
}
