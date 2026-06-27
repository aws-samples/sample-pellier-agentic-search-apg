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
 * These assertions render the component into jsdom and inspect the DOM,
 * so a strip that drew the wrong number of segments, applied the wrong
 * solid/dashed styling, or mislabelled the shipped/total fraction would
 * fail here. (A previous version of this file asserted only arithmetic on
 * the generated Segment[] and never mounted the component, which left the
 * strip's rendering — the "X/13 shipped" surface — without DOM coverage.)
 *
 * **Validates: Requirements 8.1, 9.1, 17.3**
 */
import { createElement } from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import fc from 'fast-check';
import { WorkshopProgressStrip, type Segment } from '../components/WorkshopProgressStrip';

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Status is either 'shipped' or 'exercise'. */
const statusArb = fc.constantFrom('shipped' as const, 'exercise' as const);

/**
 * Generate a single valid Segment object with a unique id. (Uniqueness is
 * enforced at the array level below so React keys don't collide.)
 */
const segmentArb: fc.Arbitrary<Omit<Segment, 'id'>> = fc.record({
  label: fc.string({ minLength: 1, maxLength: 40 }).filter((s) => s.trim().length > 0),
  status: statusArb,
});

/** Generate an array of Segment objects (0–30 items) with stable unique ids. */
const segmentsArb: fc.Arbitrary<Segment[]> = fc
  .array(segmentArb, { minLength: 0, maxLength: 30 })
  .map((items) => items.map((item, i) => ({ ...item, id: `seg-${i}` })));

/**
 * Count rendered segments by style. The strip renders one element per
 * segment: shipped segments get a green background fill, exercise segments
 * get a transparent background with a dashed red border. We read those
 * inline styles back off the DOM rather than trusting the input array.
 */
function countRenderedSegments(barEl: HTMLElement): { solid: number; dashed: number } {
  const children = Array.from(barEl.children) as HTMLElement[];
  let solid = 0;
  let dashed = 0;
  for (const child of children) {
    if (child.style.borderStyle === 'dashed' || child.style.border.includes('dashed')) {
      dashed += 1;
    } else if (child.style.backgroundColor === 'var(--at-green-1)') {
      solid += 1;
    }
  }
  return { solid, dashed };
}

// ---------------------------------------------------------------------------
// Property 3: Workshop progress strip accuracy
// ---------------------------------------------------------------------------
describe('Property 3: Workshop progress strip accuracy', () => {
  it('renders exactly as many solid segments as shipped, dashed as exercise, total as item count', () => {
    fc.assert(
      fc.property(segmentsArb, (segments) => {
        cleanup();
        const shippedCount = segments.filter((s) => s.status === 'shipped').length;
        const exerciseCount = segments.filter((s) => s.status === 'exercise').length;
        const total = segments.length;

        const { container } = render(
          createElement(WorkshopProgressStrip, { segments, shipped: shippedCount, total }),
        );

        // The segment bar carries the accessible label and holds one child
        // element per segment.
        const bar = container.querySelector('[aria-label^="Workshop progress:"]') as HTMLElement;
        expect(bar).toBeTruthy();
        expect(bar.children.length).toBe(total);

        // Solid (shipped) and dashed (exercise) counts read back off the DOM
        // must match the input partition — this is the rendering contract the
        // old arithmetic-only test never checked.
        const { solid, dashed } = countRenderedSegments(bar);
        expect(solid).toBe(shippedCount);
        expect(dashed).toBe(exerciseCount);

        // The fraction label and aria-label both report shipped/total.
        expect(bar.getAttribute('aria-label')).toBe(
          `Workshop progress: ${shippedCount} of ${total} shipped`,
        );
      }),
      { numRuns: 100 },
    );
  });

  it('all-shipped input renders all solid segments and a full fraction', () => {
    fc.assert(
      fc.property(
        fc
          .array(
            fc.record({
              label: fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
              status: fc.constant('shipped' as const),
            }),
            { minLength: 1, maxLength: 20 },
          )
          .map((items) => items.map((item, i) => ({ ...item, id: `seg-${i}` }))),
        (segments) => {
          cleanup();
          const total = segments.length;
          const { container } = render(
            createElement(WorkshopProgressStrip, { segments, shipped: total, total }),
          );

          const bar = container.querySelector('[aria-label^="Workshop progress:"]') as HTMLElement;
          const { solid, dashed } = countRenderedSegments(bar);
          expect(solid).toBe(total);
          expect(dashed).toBe(0);
          expect(screen.getByText(`${total}/${total}`)).toBeTruthy();
        },
      ),
      { numRuns: 50 },
    );
  });

  it('all-exercise input renders all dashed segments and a zero fraction', () => {
    fc.assert(
      fc.property(
        fc
          .array(
            fc.record({
              label: fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0),
              status: fc.constant('exercise' as const),
            }),
            { minLength: 1, maxLength: 20 },
          )
          .map((items) => items.map((item, i) => ({ ...item, id: `seg-${i}` }))),
        (segments) => {
          cleanup();
          const total = segments.length;
          const { container } = render(
            createElement(WorkshopProgressStrip, { segments, shipped: 0, total }),
          );

          const bar = container.querySelector('[aria-label^="Workshop progress:"]') as HTMLElement;
          const { solid, dashed } = countRenderedSegments(bar);
          expect(solid).toBe(0);
          expect(dashed).toBe(total);
          expect(screen.getByText(`0/${total}`)).toBeTruthy();
        },
      ),
      { numRuns: 50 },
    );
  });
});
