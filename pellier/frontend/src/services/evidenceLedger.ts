/**
 * Evidence ledger client.
 *
 * One durable, principal-scoped ledger per turn, read from
 * `GET /api/observatory/turns/{turn_id}/ledger`. The endpoint answers only
 * for the verified caller, so the request carries the session cookies and a
 * refusal (401, 404, 503) comes back as `null`: an absent ledger is a fact
 * the caller must render as absence, never as an empty success.
 */
import type {
  EvidenceLedger,
  EvidenceSufficiencyCheck,
} from '../shared/evidenceLedger'

import { API_BASE_URL, apiFetch } from './apiBase'

/**
 * Fetch the evidence ledger projected for one turn.
 *
 * @param turnId Stable per-turn id minted by the backend.
 * @param signal Optional abort signal for unmounting callers.
 * @returns The ledger, or `null` when the API did not return one.
 */
export async function fetchTurnEvidenceLedger(
  turnId: string,
  signal?: AbortSignal,
): Promise<EvidenceLedger | null> {
  const response = await apiFetch(
    `${API_BASE_URL}/api/observatory/turns/${encodeURIComponent(turnId)}/ledger`,
    { credentials: 'include', signal },
  )
  if (!response.ok) return null
  return (await response.json()) as EvidenceLedger
}

/**
 * Whether every required sufficiency check is satisfied.
 *
 * A check is required unless the projection marked it `not_applicable` for
 * this turn. `not_reached`, `not_enforced`, `unavailable` and `missing` are
 * all honest states, and none of them is "recorded"; an empty list is not a
 * clean bill either, because nothing was checked.
 */
export function requiredEvidenceSatisfied(
  checks: ReadonlyArray<EvidenceSufficiencyCheck>,
): boolean {
  const required = checks.filter((check) => check.status !== 'not_applicable')
  return (
    required.length > 0 && required.every((check) => check.status === 'satisfied')
  )
}
