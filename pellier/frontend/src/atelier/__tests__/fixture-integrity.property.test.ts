/**
 * Property test for fixture data round-trip integrity (Property 4)
 *
 * Property 4: Fixture data round-trip integrity — for each fixture key
 * in the Atelier fixture set, loading the fixture via useAtelierData with
 * source "fixture" SHALL return data that is structurally identical to the
 * raw JSON content of the corresponding fixture file — no fields dropped,
 * no values mutated.
 *
 * Coverage is derived from useAtelierData's own FIXTURE_KEYS export, so a
 * fixture added to the hook without a matching entry here fails the guard
 * test below rather than silently going untested.
 *
 * **Validates: Requirements 16.1**
 */
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAtelierData, FIXTURE_KEYS } from '../hooks/useAtelierData';

// Direct raw JSON imports — these are the ground-truth fixtures.
import rawSessions from '../fixtures/sessions.json';
import rawSession7f5a from '../fixtures/session-7f5a.json';
import rawSessionMarcoOpeningDemo from '../fixtures/session-marco-opening-demo.json';
import rawSessionMarcoMidpointCheckpoint from '../fixtures/session-marco-midpoint-checkpoint.json';
import rawSessionMarcoCapstone from '../fixtures/session-marco-capstone.json';
import rawSessionAnnaMorningRitual from '../fixtures/session-anna-morning-ritual.json';
import rawSessionAnnaUnder100 from '../fixtures/session-anna-under-100.json';
import rawSessionAnnaCandlePairing from '../fixtures/session-anna-candle-pairing.json';
import rawSessionAnnaBirthdayGift from '../fixtures/session-anna-birthday-gift.json';
import rawSessionAnnaHousewarming from '../fixtures/session-anna-housewarming.json';
import rawSessionTheoPourOver from '../fixtures/session-theo-pour-over.json';
import rawSessionTheoPourOverPairing from '../fixtures/session-theo-pour-over-pairing.json';
import rawSessionTheoLinenSeasons from '../fixtures/session-theo-linen-seasons.json';
import rawSessionTheoCeramicsReturn from '../fixtures/session-theo-ceramics-return.json';
import rawSessionTheoHomeNotWardrobe from '../fixtures/session-theo-home-not-wardrobe.json';
import rawAgents from '../fixtures/agents.json';
import rawTools from '../fixtures/tools.json';
import rawSkills from '../fixtures/skills.json';
import rawRouting from '../fixtures/routing.json';
import rawMemoryMarco from '../fixtures/memory-marco.json';
import rawMemoryAnna from '../fixtures/memory-anna.json';
import rawMemoryTheo from '../fixtures/memory-theo.json';
import rawPerformance from '../fixtures/performance.json';
import rawEvaluations from '../fixtures/evaluations.json';
import rawObservatory from '../fixtures/observatory.json';
import rawArchitecture from '../fixtures/architecture.json';
import rawProductionPatterns from '../fixtures/production-patterns.json';

/**
 * All fixture keys and their corresponding raw JSON data. Must stay in
 * sync with useAtelierData's fixtureImporters — the guard test below
 * cross-checks this list against the hook's FIXTURE_KEYS export.
 */
const fixtureEntries: [string, unknown][] = [
  ['sessions', rawSessions],
  ['session-7f5a', rawSession7f5a],
  ['session-marco-opening-demo', rawSessionMarcoOpeningDemo],
  ['session-marco-midpoint-checkpoint', rawSessionMarcoMidpointCheckpoint],
  ['session-marco-capstone', rawSessionMarcoCapstone],
  ['session-anna-morning-ritual', rawSessionAnnaMorningRitual],
  ['session-anna-under-100', rawSessionAnnaUnder100],
  ['session-anna-candle-pairing', rawSessionAnnaCandlePairing],
  ['session-anna-birthday-gift', rawSessionAnnaBirthdayGift],
  ['session-anna-housewarming', rawSessionAnnaHousewarming],
  ['session-theo-pour-over', rawSessionTheoPourOver],
  ['session-theo-pour-over-pairing', rawSessionTheoPourOverPairing],
  ['session-theo-linen-seasons', rawSessionTheoLinenSeasons],
  ['session-theo-ceramics-return', rawSessionTheoCeramicsReturn],
  ['session-theo-home-not-wardrobe', rawSessionTheoHomeNotWardrobe],
  ['agents', rawAgents],
  ['tools', rawTools],
  ['skills', rawSkills],
  ['routing', rawRouting],
  ['memory-marco', rawMemoryMarco],
  ['memory-anna', rawMemoryAnna],
  ['memory-theo', rawMemoryTheo],
  ['performance', rawPerformance],
  ['evaluations', rawEvaluations],
  ['observatory', rawObservatory],
  ['architecture', rawArchitecture],
  ['production-patterns', rawProductionPatterns],
];

describe('Property 4: Fixture data round-trip integrity', () => {
  it.each(fixtureEntries)(
    'useAtelierData("%s", source: "fixture") returns data identical to raw JSON import',
    async (key, rawJson) => {
      const { result } = renderHook(() =>
        useAtelierData({ key, source: 'fixture' }),
      );

      // Wait for the async fixture import to resolve
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // No error should occur when loading a valid fixture key
      expect(result.current.error).toBeNull();

      // The data returned by the hook must be deeply equal to the raw
      // JSON import — no fields dropped, no values mutated, no
      // structural differences.
      expect(result.current.data).toEqual(rawJson);
    },
  );

  it('covers every fixture key registered in useAtelierData (no silent gaps)', () => {
    // Guard: derive the expected set from the hook's own FIXTURE_KEYS export
    // rather than a hard-coded list, so adding a fixture to the hook without
    // adding a round-trip case here fails this assertion.
    const testedKeys = fixtureEntries.map(([key]) => key).sort();
    const registeredKeys = [...FIXTURE_KEYS].sort();
    expect(testedKeys).toEqual(registeredKeys);
  });
});
