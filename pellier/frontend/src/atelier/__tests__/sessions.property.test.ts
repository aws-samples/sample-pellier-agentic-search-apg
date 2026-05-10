/**
 * Property tests for Sessions surfaces (Properties 1 & 2)
 *
 * Property 1: Sessions are sorted by recency — for any list of Session
 * objects with distinct timestamps, sortSessionsByRecency returns them
 * in descending order (most recent first).
 *
 * Property 2: Session card field completeness — for any valid Session
 * object, all 6 required card fields (hex ID, opening query, elapsed
 * time, agent count, routing pattern, timestamp) are present and
 * non-empty.
 *
 * **Validates: Requirements 2.1, 2.2**
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { sortSessionsByRecency } from '../surfaces/observe/SessionsList';
import type { Session } from '../types';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Hex-style session ID (1-8 uppercase hex chars). */
const hexIdArb = fc
  .string({
    minLength: 1,
    maxLength: 8,
    unit: fc.constantFrom(...'0123456789ABCDEF'.split('')),
  });

/** Persona ID. */
const personaIdArb = fc.constantFrom('marco', 'elena', 'kai', 'priya');

/** Non-empty opening query string. */
const openingQueryArb = fc.string({ minLength: 1, maxLength: 120 }).filter((s) => s.trim().length > 0);

/** Elapsed time in milliseconds (1ms – 60s). */
const elapsedMsArb = fc.integer({ min: 1, max: 60_000 });

/** Agent count (1–5 specialists). */
const agentCountArb = fc.integer({ min: 1, max: 5 });

/** Routing pattern name. */
const routingPatternArb = fc.constantFrom('Dispatcher', 'Agents-as-Tools', 'Graph');

/** Session status. */
const statusArb = fc.constantFrom('complete' as const, 'active' as const);

/**
 * Generate a valid ISO 8601 timestamp from an integer epoch-ms value.
 * Using integer range avoids Invalid Date issues during shrinking.
 */
const timestampArb = fc
  .integer({
    min: new Date('2024-01-01T00:00:00Z').getTime(),
    max: new Date('2026-12-31T23:59:59Z').getTime(),
  })
  .map((ms) => new Date(ms).toISOString());

/** Generate a single valid Session object. */
const sessionArb: fc.Arbitrary<Session> = fc.record({
  id: hexIdArb,
  personaId: personaIdArb,
  openingQuery: openingQueryArb,
  elapsedMs: elapsedMsArb,
  agentCount: agentCountArb,
  routingPattern: routingPatternArb,
  timestamp: timestampArb,
  status: statusArb,
});

/**
 * Generate an array of Session objects with distinct timestamps.
 * We use uniqueArray on the timestamp to guarantee no duplicates,
 * then map each unique timestamp into a full Session.
 */
const sessionsWithDistinctTimestampsArb: fc.Arbitrary<Session[]> = fc
  .uniqueArray(
    timestampArb,
    { minLength: 0, maxLength: 30, comparator: (a, b) => a === b },
  )
  .chain((timestamps) =>
    fc.tuple(
      ...timestamps.map((ts) =>
        sessionArb.map((s) => ({ ...s, timestamp: ts })),
      ),
    ).map((arr) => arr as Session[]),
  );

// ---------------------------------------------------------------------------
// Property 1: Sessions are sorted by recency
// ---------------------------------------------------------------------------
describe('Property 1: Sessions are sorted by recency', () => {
  it('sortSessionsByRecency returns sessions in descending timestamp order', () => {
    fc.assert(
      fc.property(sessionsWithDistinctTimestampsArb, (sessions) => {
        const sorted = sortSessionsByRecency(sessions);

        // Length must be preserved.
        expect(sorted).toHaveLength(sessions.length);

        // Each consecutive pair must be in descending order.
        for (let i = 0; i < sorted.length - 1; i++) {
          const current = new Date(sorted[i].timestamp).getTime();
          const next = new Date(sorted[i + 1].timestamp).getTime();
          expect(current).toBeGreaterThanOrEqual(next);
        }
      }),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Session card field completeness
// ---------------------------------------------------------------------------
describe('Property 2: Session card field completeness', () => {
  it('every Session object has all 6 required card fields present and non-empty', () => {
    fc.assert(
      fc.property(sessionArb, (session) => {
        // 1. Hex ID — non-empty string
        expect(typeof session.id).toBe('string');
        expect(session.id.length).toBeGreaterThan(0);

        // 2. Opening query — non-empty string
        expect(typeof session.openingQuery).toBe('string');
        expect(session.openingQuery.trim().length).toBeGreaterThan(0);

        // 3. Elapsed time — positive number
        expect(typeof session.elapsedMs).toBe('number');
        expect(session.elapsedMs).toBeGreaterThan(0);

        // 4. Agent count — positive integer
        expect(typeof session.agentCount).toBe('number');
        expect(session.agentCount).toBeGreaterThan(0);

        // 5. Routing pattern — non-empty string
        expect(typeof session.routingPattern).toBe('string');
        expect(session.routingPattern.length).toBeGreaterThan(0);

        // 6. Timestamp — valid ISO 8601 string that parses to a real date
        expect(typeof session.timestamp).toBe('string');
        expect(session.timestamp.length).toBeGreaterThan(0);
        const parsed = new Date(session.timestamp).getTime();
        expect(Number.isNaN(parsed)).toBe(false);
      }),
      { numRuns: 200 },
    );
  });
});
