/**
 * One coordinator for every demo shopper sign-in in the browser.
 *
 * The chooser (Ask Pellier chips, the header's switcher) and the expired-session
 * "Sign in again" action each start a workshop sign-in, and each response sets the
 * shopper session cookies. Left independent, a slow response for the shopper chosen
 * first can land after the next one and leave the cookie, and every later request,
 * with the wrong shopper while the page names the right one.
 *
 * The latest request owns the session. Starting a sign-in aborts the one in flight,
 * waits for it to settle so the browser applies the responses in request order, signs
 * in, then confirms the session answers for that shopper before reporting success. A
 * superseded attempt throws `SupersededError` and applies nothing.
 */
import { PasswordAuthError, workshopSignIn, type WorkshopShopper } from './passwordAuth'

/** A newer sign-in replaced this one, so nothing it did may reach the page. */
export class SupersededError extends Error {}

interface Attempt {
  controller: AbortController
}

let latest: Attempt | null = null
let inFlight: Promise<unknown> | null = null

/** Rejects once the attempt is replaced, so a slow read cannot hold a newer one up. */
function whenSuperseded(attempt: Attempt): Promise<never> {
  return new Promise((_resolve, reject) => {
    const abandon = () => reject(new SupersededError('A newer sign-in replaced this one'))
    if (attempt.controller.signal.aborted) abandon()
    else attempt.controller.signal.addEventListener('abort', abandon, { once: true })
  })
}

async function run(
  attempt: Attempt,
  shopper: WorkshopShopper,
  readSession: () => Promise<string | null>,
  previous: Promise<unknown> | null,
): Promise<void> {
  const superseded = whenSuperseded(attempt)
  superseded.catch(() => {})
  try {
    if (previous) await Promise.race([previous, superseded])
    await workshopSignIn(shopper, attempt.controller.signal)
    const verified = await Promise.race([readSession(), superseded])
    if (latest !== attempt) throw new SupersededError('A newer sign-in replaced this one')
    if (verified === null) throw new PasswordAuthError('auth_unavailable')
    if (verified !== shopper) throw new PasswordAuthError('session_mismatch')
  } catch (reason) {
    if (reason instanceof SupersededError || attempt.controller.signal.aborted) {
      throw new SupersededError('A newer sign-in replaced this one')
    }
    throw reason
  }
}

/**
 * Sign `shopper` in and confirm the session. `readSession` re-reads who the server says
 * is signed in (`/api/auth/me`) and resolves their lowercased username. Resolves when the
 * session belongs to `shopper`; rejects with `SupersededError` when a newer sign-in
 * replaced this one, or with the failure otherwise.
 */
export function signInShopper(
  shopper: WorkshopShopper,
  readSession: () => Promise<string | null>,
): Promise<void> {
  latest?.controller.abort()
  const attempt: Attempt = { controller: new AbortController() }
  latest = attempt
  const result = run(attempt, shopper, readSession, inFlight)
  const settled = result.then(() => {}, () => {}).then(() => {
    if (inFlight === settled) inFlight = null
  })
  inFlight = settled
  return result
}

/** Abandon the sign-in in flight, if any, so a late response cannot undo a sign-out. */
export function cancelShopperSignIn(): void {
  latest?.controller.abort()
  latest = null
}
