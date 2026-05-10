/**
 * Property test for fixture data round-trip integrity (Property 4)
 *
 * Property 4: Fixture data round-trip integrity — for each fixture key
 * in the Atelier fixture set, loading the fixture via useAtelierData with
 * source "fixture" SHALL return data that is structurally identical to the
 * raw JSON content of the corresponding fixture file — no fields dropped,
 * no values mutated.
 *
 * **Validates: Requirements 16.1**
 */
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAtelierData } from '../hooks/useAtelierData';

// Direct raw JSON imports — these are the ground-truth fixtures.
import rawSessions from '../fixtures/sessions.json';
import rawSession7f5a from '../fixtures/session-7f5a.json';
import rawAgents from '../fixtures/agents.json';
import rawTools from '../fixtures/tools.json';
import rawRouting from '../fixtures/routing.json';
import rawMemoryMarco from '../fixtures/memory-marco.json';
import rawPerformance from '../fixtures/performance.json';
import rawEvaluations from '../fixtures/evaluations.json';
import rawObservatory from '../fixtures/observatory.json';
import rawArchitecture from '../fixtures/architecture.json';

/**
 * All fixture keys and their corresponding raw JSON data.
 * This is the complete set defined in the design document.
 */
const fixtureEntries: [string, unknown][] = [
  ['sessions', rawSessions],
  ['session-7f5a', rawSession7f5a],
  ['agents', rawAgents],
  ['tools', rawTools],
  ['routing', rawRouting],
  ['memory-marco', rawMemoryMarco],
  ['performance', rawPerformance],
  ['evaluations', rawEvaluations],
  ['observatory', rawObservatory],
  ['architecture', rawArchitecture],
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

  it('all 10 fixture keys are covered by this test', () => {
    // Guard: ensure we're testing the complete fixture set defined in
    // the design document, not a subset.
    const expectedKeys = [
      'sessions',
      'session-7f5a',
      'agents',
      'tools',
      'routing',
      'memory-marco',
      'performance',
      'evaluations',
      'observatory',
      'architecture',
    ];
    const testedKeys = fixtureEntries.map(([key]) => key);
    expect(testedKeys).toEqual(expectedKeys);
    expect(testedKeys).toHaveLength(10);
  });
});
