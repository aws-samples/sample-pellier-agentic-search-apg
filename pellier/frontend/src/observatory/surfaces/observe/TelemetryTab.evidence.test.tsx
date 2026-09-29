import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionDetail, TelemetryPanel } from '../../types';
import type { SessionOutletContext } from './SessionView';
import TelemetryTab, { evidenceFooterStats } from './TelemetryTab';

const mocks = vi.hoisted(() => ({ useObservatoryData: vi.fn() }));
vi.mock('../../hooks/useObservatoryData', () => ({
  useObservatoryData: (options: { key: string }) => mocks.useObservatoryData(options),
}));

const hybrid: TelemetryPanel = {
  index: 1,
  category: 'owned',
  title: 'search_products_hybrid',
  description: 'agent invocation recorded in Aurora.',
  status: 'succeeded',
  durationMs: 1168,
  agent: 'agent',
  eventKind: 'tool',
  provenance: 'aurora-receipt',
  rows: [{
    args: { query: 'ceramics', turn_id: 'turn-d224e15a874145eebe8545ca10be82f2' },
    result: {
      pool_size: 21,
      search_method: 'hybrid+rerank',
      products: [
        { productId: '31', name: 'Stoneware Pour-Over Set', price: 165, rrf_score: 0.03279, rerank_score: 0.797 },
        { productId: '44', name: 'Olive Branch Vessel', price: 185, rrf_score: 0.03008, rerank_score: 0.286 },
        { productId: '12', name: 'Ceramic Tumblers', price: 78, rrf_score: 0.03226, rerank_score: 0.231 },
      ],
    },
  }],
};

const refused: TelemetryPanel = {
  index: 2,
  category: 'owned',
  title: 'initiate_return',
  description: 'Refused before execution: governed writes run on the managed rail. The refusal is recorded in Aurora.',
  status: 'denied',
  durationMs: 12,
  agent: 'agent',
  eventKind: 'tool',
  provenance: 'aurora-receipt',
  rows: [{ args: {}, result: { tool: 'initiate_return', error: 'managed_rail_required' } }],
};

const session: SessionDetail = {
  id: 'persona-theo-test',
  personaId: 'theo',
  openingQuery: 'hand-thrown ceramics slow morning ritual stoneware pour-over',
  elapsedMs: 96474,
  agentCount: 1,
  routingPattern: 'Storefront Dispatcher',
  timestamp: '2026-09-28T02:11:00.000Z',
  status: 'complete',
  chat: [],
  telemetry: [hybrid, refused],
  evidenceLedger: null,
  brief: { folioNumber: 0, headline: 'Recorded', filedTime: '2026-09-28T02:11:00.000Z', sections: [], products: [] },
};

function renderTab() {
  const Harness = () => <Outlet context={{ session, replayNonce: 0 } satisfies SessionOutletContext} />;
  return render(
    <MemoryRouter initialEntries={['/telemetry']}>
      <Routes>
        <Route element={<Harness />}>
          <Route path="/telemetry" element={<TelemetryTab />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('session evidence at depth', () => {
  beforeEach(() => {
    mocks.useObservatoryData.mockReturnValue({
      data: { models: [
        { role: 'editorial', label: 'Editorial specialists', setting: 'BEDROCK_OPUS_MODEL', modelId: 'global.anthropic.claude-opus-4-6-v1' },
        { role: 'rerank', label: 'Rerank', setting: 'BEDROCK_RERANK_MODEL', modelId: null },
      ] },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it('folds context into one closed disclosure ahead of the first tool call', () => {
    renderTab();
    const context = screen.getByText('Routing pattern, configured models and timeline mode').closest('details')!;
    expect(context).not.toHaveAttribute('open');
    expect(screen.getByTestId('hybrid-search-result')).toBeInTheDocument();
  });

  it('reads the configured models from the backend and marks an unset one', () => {
    renderTab();
    expect(mocks.useObservatoryData).toHaveBeenCalledWith({ key: 'models' });
    const models = screen.getByRole('region', { name: 'Models this deployment is configured to use', hidden: true });
    expect(within(models).getByText('global.anthropic.claude-opus-4-6-v1')).toBeInTheDocument();
    expect(within(models).getByText('Rerank').nextElementSibling).toHaveTextContent('—');
    expect(screen.queryByText(/Claude Opus 5/)).not.toBeInTheDocument();
  });

  it('shows the recorded ranking with movement named, not coloured only', () => {
    renderTab();
    const table = within(screen.getByTestId('hybrid-search-result')).getByRole('table');
    const olive = within(table).getByRole('row', { name: /Olive Branch Vessel/ });
    expect(within(olive).getByLabelText('Up 1 place from RRF order')).toHaveTextContent('▲ 1');
    expect(screen.getByText(/the fused pool held 21 candidates/)).toBeInTheDocument();
    expect(screen.getByText(/Raw arguments and result \(\d[\d,]* characters\)/)).toBeInTheDocument();
  });

  it('counts successes as a count over the steps it saw', () => {
    renderTab();
    expect(screen.getByText('1 of 2').nextElementSibling).toHaveTextContent('Succeeded');
    expect(screen.queryByText(/Success rate/)).not.toBeInTheDocument();
  });
});

describe('evidence footer counts', () => {
  it('treats a recorded success as success and never counts a refusal as one', () => {
    expect(evidenceFooterStats([hybrid, refused])).toEqual({ agents: 1, stepsWithSql: 0, steps: 2, succeeded: 1 });
    expect(evidenceFooterStats([{ ...hybrid, status: 'complete', sql: 'SELECT 1' }])).toMatchObject({ stepsWithSql: 1, succeeded: 1 });
    expect(evidenceFooterStats([])).toEqual({ agents: 0, stepsWithSql: 0, steps: 0, succeeded: 0 });
  });
});
