/**
 * Conversation history for the guided requests returned by Aurora.
 *
 * The journey advertises that each turn keeps the previous conversation, so
 * turn N must be sent with the N-1 completed exchanges before it, and it
 * cannot run until they exist. Entries are indexed by turn so a rerun of an
 * earlier turn restarts the thread from that point rather than splicing a
 * fresh answer into a stale tail.
 */
import type { ChatMessage, ChatProduct } from '../../../services/chat';

export interface GuidedTurnEntry {
  query: string;
  answer: string;
  products: ChatProduct[];
}

export type GuidedTurnEntries = ReadonlyArray<GuidedTurnEntry | undefined>;

/** Record a completed turn and drop everything that followed it. */
export function completeTurn(
  entries: GuidedTurnEntries,
  index: number,
  entry: GuidedTurnEntry,
): GuidedTurnEntry[] {
  const next: GuidedTurnEntry[] = [];
  for (let position = 0; position < index; position += 1) {
    const previous = entries[position];
    if (previous) next[position] = previous;
  }
  next[index] = entry;
  return next;
}

/**
 * Legacy scenario responses have three required turns. Current responses
 * carry explicit roles; their actual count is passed by the request rail.
 */
export const REQUIRED_TURN_COUNT = 3;

/**
 * Whether the request at `index` may start.
 *
 * Turn N may run once turn N-1 has a completed entry. Explore prompts are
 * side excursions rather than later turns of that conversation, so they run
 * whenever the workbench is idle.
 *
 * Both the enabled state of a request button and the run's own guard read
 * this one answer. Two spellings of the rule drifted once already and left an
 * enabled button that did nothing when pressed.
 */
export function canRunTurn(
  entries: GuidedTurnEntries,
  index: number,
  requiredTurnCount = REQUIRED_TURN_COUNT,
): boolean {
  if (index >= requiredTurnCount) return true;
  return index === 0 || Boolean(entries[index - 1]);
}

/**
 * The user/assistant pairs for every completed turn before `index`, in
 * order. Gating guarantees they are contiguous; a gap means the thread was
 * restarted and the later entries are not part of this conversation.
 */
export function historyForTurn(
  entries: GuidedTurnEntries,
  index: number,
): ChatMessage[] {
  const history: ChatMessage[] = [];
  for (let position = 0; position < index; position += 1) {
    const entry = entries[position];
    if (!entry) break;
    const timestamp = new Date();
    history.push({ role: 'user', content: entry.query, timestamp });
    history.push({
      role: 'assistant',
      content: entry.answer,
      timestamp,
      products: entry.products,
    });
  }
  return history;
}
