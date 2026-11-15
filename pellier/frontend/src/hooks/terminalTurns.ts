/**
 * Terminal turns Ask Pellier has shown, and the conversation each was shown in.
 *
 * The relay replays a shopper's recent terminal turns to every new watch. A turn
 * belongs to the conversation (the server session in `pellier-session-id`) that was
 * open when it first appeared, so this record keeps it there across a remount, a
 * reload, and a New conversation that lands while the panel is closed. One shopper's
 * record at a time: another shopper's watch, and a sign-out, discard it.
 */
const SHOWN_KEY = 'pellier-terminal-shown'
const SESSION_KEY = 'pellier-session-id'
const LIMIT = 20

/** The conversation open now: the session a new turn is shown in. */
export function currentSession(): string {
  try {
    return localStorage.getItem(SESSION_KEY) ?? ''
  } catch {
    return ''
  }
}

/** This shopper's shown turns, by turn id, each with its session. */
export function readShownTurns(shopper: string): Map<string, string> {
  try {
    const saved = JSON.parse(localStorage.getItem(SHOWN_KEY) ?? 'null')
    if (saved?.shopper === shopper && saved.turns && typeof saved.turns === 'object') {
      return new Map(
        Object.entries(saved.turns as Record<string, unknown>)
          .filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
      )
    }
    localStorage.removeItem(SHOWN_KEY)
  } catch {
    // Unreadable storage: this page knows of no earlier turn.
  }
  return new Map()
}

export function saveShownTurns(shopper: string, turns: Map<string, string>): void {
  try {
    const kept = Object.fromEntries([...turns].slice(-LIMIT))
    localStorage.setItem(SHOWN_KEY, JSON.stringify({ shopper, turns: kept }))
  } catch {
    // Quota or blocked storage: the map still holds them while this page stays open.
  }
}

export function clearShownTurns(): void {
  try {
    localStorage.removeItem(SHOWN_KEY)
  } catch {
    // Nothing stored that could be read back.
  }
}
