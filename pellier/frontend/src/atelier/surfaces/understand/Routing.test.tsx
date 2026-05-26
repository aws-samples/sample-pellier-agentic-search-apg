/**
 * Routing surface — LangGraph comparison card tests.
 *
 * Pins the editorial contract for the "Coming from LangGraph" card:
 *   - The card renders alongside the three pattern cards.
 *   - Three mapping rows are present, one per Pellier pattern, each with
 *     a non-empty LangGraph analogue and a key-difference cell.
 *   - The "when to reach for LangGraph" copy lists the three workflow
 *     shapes that justify a graph runtime — durable checkpointing,
 *     human-in-the-loop, cycle-heavy topology — so a copy edit that
 *     drops one of them trips the test.
 *
 * Mocks `useAtelierData` to return the routing fixture synchronously,
 * skipping the dynamic-import code path the way ProductionPatterns.test
 * does.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TEST_ROUTER_FUTURE_FLAGS } from '../../../test-utils';
import routingRaw from '../../fixtures/routing.json';
import type { RoutingPattern } from '../../types';

vi.mock('../../hooks/useAtelierData', () => ({
  useAtelierData: () => ({
    data: routingRaw as unknown as RoutingPattern[],
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

import Routing from './Routing';

const renderRouting = () =>
  render(
    <MemoryRouter future={TEST_ROUTER_FUTURE_FLAGS}>
      <Routing />
    </MemoryRouter>,
  );

describe('Routing surface · LangGraph comparison card', () => {
  it('renders the comparison card with all three Pellier-pattern rows', () => {
    renderRouting();

    const table = screen.getByTestId('langgraph-comparison-table');
    expect(table).toBeInTheDocument();

    // One row per Pellier pattern. The data-testid stems use the first
    // word of the pattern name lowercased.
    const dispatcherRow = screen.getByTestId('langgraph-row-dispatcher');
    const aatRow = screen.getByTestId('langgraph-row-agents-as-tools');
    const graphRow = screen.getByTestId('langgraph-row-graph');

    for (const row of [dispatcherRow, aatRow, graphRow]) {
      // Each row has three populated cells (Pellier / LangGraph / diff).
      const cells = within(row).getAllByRole('cell');
      expect(cells).toHaveLength(3);
      for (const cell of cells) {
        expect(cell.textContent?.trim().length ?? 0).toBeGreaterThan(0);
      }
    }
  });

  it('maps each pattern to a recognizable LangGraph concept', () => {
    renderRouting();

    // Dispatcher → conditional edges from a router node
    expect(
      screen.getByTestId('langgraph-row-dispatcher').textContent?.toLowerCase(),
    ).toContain('conditional edge');

    // Agents-as-Tools → supervisor pattern
    expect(
      screen.getByTestId('langgraph-row-agents-as-tools').textContent?.toLowerCase(),
    ).toContain('supervisor');

    // Graph → StateGraph
    expect(
      screen.getByTestId('langgraph-row-graph').textContent,
    ).toContain('StateGraph');
  });

  it('frames the "three patterns, not one graph" editorial header', () => {
    renderRouting();
    // The serif header anchors the editorial difference. A copy edit that
    // drops "graph" from the header should trip this assertion.
    expect(
      screen.getByText(/three patterns, not one graph/i),
    ).toBeInTheDocument();
  });

  it('lists the three workflow shapes that justify a graph runtime', () => {
    renderRouting();
    // The "when to reach for LangGraph instead" footer is the operator
    // takeaway — losing any of the three shapes would weaken the contrast.
    const card = screen.getByTestId('langgraph-comparison-table').closest('div');
    const copy = card?.textContent?.toLowerCase() ?? '';
    expect(copy).toContain('checkpoint');
    expect(copy).toContain('human-in-the-loop');
    expect(copy).toMatch(/cycle|planner.*critic|topology/);
  });
});
