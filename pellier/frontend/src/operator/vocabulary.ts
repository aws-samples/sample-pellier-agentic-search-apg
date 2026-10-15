/**
 * What the desk's three counts mean, defined once so every surface says the
 * same thing.
 *
 * - **Open request**: a client's chat request for a store credit that no
 *   investigation has answered yet. The Clients list counts them per client
 *   and in total; the Reviews rail lists them under Requests.
 * - **Review**: one proposed credit with its decision, decided or not. The
 *   Reviews section lists every review.
 * - **Waiting for approval**: a review no person has approved or declined.
 *   The Reviews badge, the rail's count and every waiting tag count exactly
 *   these, and nothing else.
 */

export const WAITING_TAG = 'Waiting for approval'

export function waitingLabel(count: number): string {
  return `${count} waiting for approval`
}

export function openRequestsLabel(count: number): string {
  return count === 1 ? '1 open request' : `${count} open requests`
}
