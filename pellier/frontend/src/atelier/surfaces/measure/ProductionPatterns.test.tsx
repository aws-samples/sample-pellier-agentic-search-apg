/**
 * ProductionPatterns surface tests — Identity card wiring strip + namespace
 * accuracy.
 *
 * Coverage:
 *   - The fixture's IdentityPattern carries a `wiring` array with five
 *     lifecycle steps anchored to the files that own each hop. This test
 *     pins the contract so a rename in the wiring strip never silently
 *     drifts from the actual code anchors.
 *   - The Identity card renders the lifecycle strip with all five steps.
 *   - Namespace strings in the fixture use the canonical dash-separated
 *     form (matches AgentCoreIdentityService.build_namespace) — colons
 *     would fail at the AgentCore session-id regex, so this guards
 *     against the drift Batch 4 fixed.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TEST_ROUTER_FUTURE_FLAGS } from '../../../test-utils';
import productionPatternsRaw from '../../fixtures/production-patterns.json';
import type { IdentityPattern, ProductionPatternsData } from '../../types';

// useAtelierData is mocked to return the raw fixture synchronously so the
// surface renders without going through the dynamic-import code path.
vi.mock('../../hooks/useAtelierData', () => ({
  useAtelierData: () => ({
    data: productionPatternsRaw as unknown as ProductionPatternsData,
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

import ProductionPatterns from './ProductionPatterns';

const data = productionPatternsRaw as unknown as ProductionPatternsData;
const identity = data.patterns.find(
  (p): p is IdentityPattern => p.slug === 'identity',
);

describe('ProductionPatterns fixture · Identity', () => {
  it('Identity pattern is present', () => {
    expect(identity).toBeDefined();
  });

  it('namespace pattern uses dashes, not colons (AgentCore session-id regex)', () => {
    // AgentCore session IDs must match [a-zA-Z0-9][a-zA-Z0-9-_]* — colons
    // are rejected at the API boundary, so the namespace must use dashes.
    // This guards against the Batch 4 drift where the fixture documented
    // a colon form that would 400 against real AgentCore.
    expect(identity!.namespacePattern.anon).toBe('anon-{session_id}');
    expect(identity!.namespacePattern.signedIn).toBe(
      'user-{cognito_sub}-session-{session_id}',
    );
    expect(identity!.namespacePattern.anon).not.toContain(':');
    expect(identity!.namespacePattern.signedIn).not.toContain(':');
  });

  it('wiring strip lists exactly 5 lifecycle hops, each with a file anchor', () => {
    expect(identity!.wiring).toHaveLength(5);
    for (const step of identity!.wiring) {
      expect(step.label.length).toBeGreaterThan(0);
      expect(step.detail.length).toBeGreaterThan(0);
      // Every anchor names a file path so operators can read the diff
      // alongside the surface.
      expect(step.anchor).toMatch(/\.(ts|tsx|py)\b|\/(frontend|backend)\//);
    }
  });

  it('wiring covers the full Cognito → namespace chain', () => {
    const labels = identity!.wiring.map((s) => s.label.toLowerCase());
    // The five hops must cover (in order): Cognito, frontend storage,
    // outgoing request, backend identity, namespace handoff. Spot-check
    // the chain by keyword so the test survives copy edits.
    expect(labels[0]).toContain('cognito');
    expect(labels.some((l) => l.includes('frontend'))).toBe(true);
    expect(labels.some((l) => l.includes('request'))).toBe(true);
    expect(labels.some((l) => l.includes('backend') || l.includes('identity'))).toBe(true);
    expect(labels[labels.length - 1]).toMatch(/namespace|memory/);
  });
});

describe('ProductionPatterns surface · Identity card render', () => {
  it('renders the identity-wiring strip with all 5 steps and their anchors', () => {
    render(
      <MemoryRouter future={TEST_ROUTER_FUTURE_FLAGS}>
        <ProductionPatterns />
      </MemoryRouter>,
    );

    const strip = screen.getByTestId('identity-wiring');
    expect(strip).toBeInTheDocument();

    for (let i = 0; i < 5; i++) {
      const step = screen.getByTestId(`identity-wiring-step-${i}`);
      expect(step).toBeInTheDocument();
      // Each step renders its anchor so the file/function is visible
      // alongside the prose.
      expect(step.textContent).toContain(identity!.wiring[i].label);
      expect(step.textContent).toContain(identity!.wiring[i].anchor);
    }
  });

  it('renders both anon and signed-in namespace cards in dash form', () => {
    render(
      <MemoryRouter future={TEST_ROUTER_FUTURE_FLAGS}>
        <ProductionPatterns />
      </MemoryRouter>,
    );

    // Both namespace patterns are rendered as <code> blocks; querying by
    // text covers both.
    expect(screen.getByText('anon-{session_id}')).toBeInTheDocument();
    expect(
      screen.getByText('user-{cognito_sub}-session-{session_id}'),
    ).toBeInTheDocument();
  });
});
