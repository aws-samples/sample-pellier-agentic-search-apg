import { describe, expect, it } from 'vitest';

import {
  REQUIRED_TURN_COUNT,
  canRunTurn,
  completeTurn,
  historyForTurn,
  type GuidedTurnEntry,
} from './guidedHistory';

function entry(index: number): GuidedTurnEntry {
  return {
    query: `question ${index}`,
    answer: `answer ${index}`,
    products: [],
  };
}

describe('guided turn history', () => {
  it('sends zero, two, then four prior messages for turns 1..3', () => {
    let entries: Array<GuidedTurnEntry | undefined> = [];
    expect(historyForTurn(entries, 0)).toHaveLength(0);

    entries = completeTurn(entries, 0, entry(0));
    expect(historyForTurn(entries, 1)).toHaveLength(2);

    entries = completeTurn(entries, 1, entry(1));
    const history = historyForTurn(entries, 2);
    expect(history).toHaveLength(4);
    expect(history.map((message) => [message.role, message.content])).toEqual([
      ['user', 'question 0'],
      ['assistant', 'answer 0'],
      ['user', 'question 1'],
      ['assistant', 'answer 1'],
    ]);
  });

  it('gates turn N on turn N-1 having completed', () => {
    const entries = completeTurn([], 0, entry(0));
    expect(canRunTurn(entries, 0)).toBe(true);
    expect(canRunTurn(entries, 1)).toBe(true);
    expect(canRunTurn(entries, 2)).toBe(false);
  });

  it('exempts explore prompts, which are excursions rather than turn 4', () => {
    expect(canRunTurn([], REQUIRED_TURN_COUNT)).toBe(true);
    expect(canRunTurn([], REQUIRED_TURN_COUNT + 1)).toBe(true);
  });

  it('uses the current required count rather than treating every third request as required', () => {
    expect(canRunTurn([], 1, 1)).toBe(true);
    expect(canRunTurn([], 1, 2)).toBe(false);
    expect(canRunTurn([], 2, 2)).toBe(true);
    expect(canRunTurn(completeTurn([], 0, entry(0)), 1, 2)).toBe(true);
  });

  it('restarts the thread when an earlier turn is rerun', () => {
    let entries = completeTurn([], 0, entry(0));
    entries = completeTurn(entries, 1, entry(1));
    entries = completeTurn(entries, 0, { ...entry(0), answer: 'revised' });

    expect(canRunTurn(entries, 2)).toBe(false);
    expect(historyForTurn(entries, 1).map((m) => m.content)).toEqual([
      'question 0',
      'revised',
    ]);
  });
});
