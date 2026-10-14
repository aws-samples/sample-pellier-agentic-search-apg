/**
 * A turn sent from the terminal (`lab_run.py send`) as `/api/chat/watch`
 * relays it: `relay_turn`, then each of the turn's own stream events inside a
 * `relay_event`, then `relay_end`. Built from the recorded Anna turn, so the
 * panel renders the same Router step, search and How it ranked.
 */
import { ANNA_QUESTION, ANNA_TURN_EVENTS } from './anna-turn'

export const TERMINAL_TURN_ID = 'turn-' + 'a'.repeat(32)

export function relayFrames(replay = false): object[] {
  return [
    {
      type: 'relay_turn',
      turn_id: TERMINAL_TURN_ID,
      session_id: 'persona-anna-terminal',
      message: ANNA_QUESTION,
      source: 'terminal',
      started_at: new Date().toISOString(),
      replay,
    },
    ...ANNA_TURN_EVENTS.map(event => ({ type: 'relay_event', turn_id: TERMINAL_TURN_ID, event })),
    { type: 'relay_end', turn_id: TERMINAL_TURN_ID, outcome: 'complete' },
  ]
}

/** How long a live relay waits before sending a frame, so the trace streams as a real turn does. */
export function liveDelayMs(frame: { type?: string; event?: { type?: string; status?: string } }): number {
  const event = frame.event
  if (!event) return 400
  if (event.type === 'content_delta') return 28
  if (event.type === 'step') return event.status === 'running' ? 700 : 1500
  if (event.type === 'product') return 150
  return 350
}
