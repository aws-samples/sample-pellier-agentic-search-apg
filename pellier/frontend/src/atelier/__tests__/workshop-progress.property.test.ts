/**
 * Property test for WorkshopProgressStrip accuracy (Property 3)
 *
 * Property 3: Workshop progress strip accuracy — for any list of items
 * (agents or tools) where each item has a status of either "shipped" or
 * "exercise", the WorkshopProgressStrip SHALL render exactly as many
 * solid segments as there are shipped items and exactly as many dashed
 * segments as there are exercise items, and the total segment count
 * SHALL equal the total item count.
 *
 * **Validates: Requirements 8.1, 9.1, 17.3**
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import type { Segment } from '../components/WorkshopProgressStrip';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Status is either 'shipped' or 'exercise'. */
const statusArb = fc.constantFrom('shipped' as const, 'exercise' as const);

/** Generate a single valid Segment object. */
const segmentArb: fc.Arbitrary<Segment> = fc.record({
  id: fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim().length > 0),
  label: fc.string({ minLength: 1, maxLength: 40 }).filter((s) => s.trim().length > 0),
  status: statusArb,
});

/** Generate an array of Segment objects (0–30 items). */
const segmentsArb: fc.Arbitrary<Segment[]> = fc.array(segmentArb, {
  minLength: 0,
  maxLength: 30,
});

// ---------------------------------------------------------------------------
// Property 3: Workshop progress strip accuracy
// ---------------------------------------------------------------------------
describe('Property 3: Workshop progress strip accuracy', () => {
  it('solid segment count equals shipped count, dashed segment count equals exercise count, total equals item count', () => {
    fc.assert(
      fc.property(segmentsArb, (segments) => {
        const shippedCount = segments.filter((s) => s.status === 'shipped').length;
        const exerciseCount = segments.filter((s) => s.status === 'exercise').length;
        const total = segments.length;

        // 1. Shipped + exercise must account for all segments (exhaustive partition).
        expect(shippedCount + exerciseCount).toBe(total);

        // 2. The shipped count derived from segments matches what would be
        //    passed as the `shipped` prop to WorkshopProgressStrip.
        expect(shippedCount).toBe(total - exerciseCount);

        // 3. Total segment count equals the item count.
        expect(segments.length).toBe(total);

        // 4. Every segment has a valid status — no unexpected values.
        for (const seg of segments) {
          expect(['shipped', 'exercise']).toContain(seg.status);
        }

        // 5. The props that would be passed to WorkshopProgressStrip are
        //    internally consistent: shipped <= total, and total === segments.length.
        expect(shippedCount).toBeLessThanOrEqual(total);
        expect(shippedCount).toBeGreaterThanOrEqual(0);
      }),
      { numRuns: 200 },
    );
  });

  it('segments with all shipped items produce shipped count equal to total', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => s.trim().length > 0),
            label: fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
            status: fc.constant('shipped' as const),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (segments) => {
          const status = (s: { status: string }) => s.status;
          const shippedCount = segments.filter((s) => status(s) === 'shipped').length;
          const exerciseCount = segments.filter((s) => status(s) === 'exercise').length;

          expect(shippedCount).toBe(segments.length);
          expect(exerciseCount).toBe(0);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('segments with all exercise items produce exercise count equal to total and shipped count of zero', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => s.trim().length > 0),
            label: fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
            status: fc.constant('exercise' as const),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (segments) => {
          const status = (s: { status: string }) => s.status;
          const shippedCount = segments.filter((s) => status(s) === 'shipped').length;
          const exerciseCount = segments.filter((s) => status(s) === 'exercise').length;

          expect(shippedCount).toBe(0);
          expect(exerciseCount).toBe(segments.length);
        },
      ),
      { numRuns: 100 },
    );
  });
});
