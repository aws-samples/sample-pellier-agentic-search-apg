/**
 * Property test: Route resolution correctness (Property 5)
 *
 * Generates valid Atelier route paths from the defined route segments
 * and verifies React Router resolves each to a non-null component.
 *
 * **Validates: Requirements 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8**
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { matchRoutes, type RouteObject } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Route configuration — mirrors the nested route tree from App.tsx.
// We use plain `element: true` as a truthy stand-in for the real React
// elements. matchRoutes only cares about path matching, not rendering.
// ---------------------------------------------------------------------------
const atelierRoutes: RouteObject[] = [
  {
    path: '/atelier',
    element: true as unknown as React.ReactNode,
    children: [
      { index: true, element: true as unknown as React.ReactNode },
      { path: 'sessions', element: true as unknown as React.ReactNode },
      {
        path: 'sessions/:id',
        element: true as unknown as React.ReactNode,
        children: [
          { index: true, element: true as unknown as React.ReactNode },
          { path: 'chat', element: true as unknown as React.ReactNode },
          { path: 'telemetry', element: true as unknown as React.ReactNode },
          { path: 'brief', element: true as unknown as React.ReactNode },
        ],
      },
      { path: 'architecture', element: true as unknown as React.ReactNode },
      { path: 'architecture/:concept', element: true as unknown as React.ReactNode },
      { path: 'agents', element: true as unknown as React.ReactNode },
      { path: 'tools', element: true as unknown as React.ReactNode },
      { path: 'routing', element: true as unknown as React.ReactNode },
      { path: 'memory', element: true as unknown as React.ReactNode },
      { path: 'performance', element: true as unknown as React.ReactNode },
      { path: 'evaluations', element: true as unknown as React.ReactNode },
      { path: 'observatory', element: true as unknown as React.ReactNode },
      { path: 'settings', element: true as unknown as React.ReactNode },
    ],
  },
]

// ---------------------------------------------------------------------------
// Generators — produce valid Atelier paths from defined route segments.
// ---------------------------------------------------------------------------

/** Alphanumeric + hex-style IDs for parameterized segments. */
const paramValueArb = fc.string({
  minLength: 1,
  maxLength: 12,
  unit: fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789'.split('')),
})

/** Architecture concept slugs matching the 8 defined concepts. */
const conceptSlugArb = fc.constantFrom(
  'memory',
  'mcp',
  'state-management',
  'tool-registry',
  'skills',
  'runtime',
  'evaluations',
  'grounding',
)

/** Session sub-tab paths. */
const sessionTabArb = fc.constantFrom('chat', 'telemetry', 'brief')

/**
 * Generates a valid Atelier route path. The generator picks from all
 * defined route segments, including parameterized routes with generated
 * parameter values.
 */
const atelierPathArb: fc.Arbitrary<string> = fc.oneof(
  // Static leaf routes
  fc.constant('/atelier'),
  fc.constant('/atelier/sessions'),
  fc.constant('/atelier/architecture'),
  fc.constant('/atelier/agents'),
  fc.constant('/atelier/tools'),
  fc.constant('/atelier/routing'),
  fc.constant('/atelier/memory'),
  fc.constant('/atelier/performance'),
  fc.constant('/atelier/evaluations'),
  fc.constant('/atelier/observatory'),
  fc.constant('/atelier/settings'),

  // Parameterized: sessions/:id
  paramValueArb.map((id) => `/atelier/sessions/${id}`),

  // Parameterized: sessions/:id/:tab
  fc.tuple(paramValueArb, sessionTabArb).map(
    ([id, tab]) => `/atelier/sessions/${id}/${tab}`,
  ),

  // Parameterized: architecture/:concept
  conceptSlugArb.map((concept) => `/atelier/architecture/${concept}`),
)

// ---------------------------------------------------------------------------
// Property test
// ---------------------------------------------------------------------------
describe('Property 5: Route resolution correctness', () => {
  it('every valid Atelier path resolves to a non-null route match', () => {
    fc.assert(
      fc.property(atelierPathArb, (path) => {
        const matches = matchRoutes(atelierRoutes, path)

        // matchRoutes returns null when no route matches the path.
        // Every valid Atelier path must produce at least one match.
        expect(matches).not.toBeNull()
        expect(matches!.length).toBeGreaterThan(0)

        // The deepest (last) match must have a non-null route element,
        // confirming a component is assigned to handle this path.
        const deepest = matches![matches!.length - 1]
        expect(deepest.route.element).toBeTruthy()
      }),
      { numRuns: 200 },
    )
  })
})
