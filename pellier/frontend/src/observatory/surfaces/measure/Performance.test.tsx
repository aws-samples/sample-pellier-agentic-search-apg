import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Performance from './Performance';
import { CANONICAL_ANNA_QUERY } from '../../constants/canonicalQuery';
vi.mock('../../hooks/useObservatoryData', () => ({ useObservatoryData: () => ({ data: { sampleCount: 0, searchStrategies: [] }, loading: false, error: null }) }));
const payload = () => ({
  query: CANONICAL_ANNA_QUERY, sharedQueryEmbeddingObservedMs: 15,
  receipt: { comparisonId: 'comparison-test', persisted: true },
  strategies: [{ strategy: 'agentic (Sonnet → filter → hybrid → rerank)', observedMs: 127, modeledCostPerThousandUsd: 4.2,
    products: [{ productId: 4, name: 'Live candle' }],
    rerank: { status: 'fallback', candidates: 20, returned: 5, model: 'cohere', fallbackOrder: 'rrf' },
    extractedFilters: { priceMaxUsd: 100, inStockOnly: true, filterUsed: 'drop_tags', categories: ['Home'], tags: ['gift'], softSignal: 'morning ritual' },
    searchPlan: { hard: { price_max_usd: 100 } }, hardConstraintsEnforced: ['price'], relaxations: [{ step: 'drop_tags' }],
  }],
});
function view() { return render(<MemoryRouter><Performance /></MemoryRouter>); }
beforeEach(() => vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload() }))));
afterEach(() => vi.unstubAllGlobals());

describe('Retrieval experiments without existing telemetry', () => {
  it('offers both experiments without fabricated baselines or automatic requests', () => {
    view();
    expect(screen.getByRole('button', { name: 'Run on Aurora' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Run both pools on Aurora' })).toBeEnabled();
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText(/fixture baseline/)).toBeNull();
    expect(screen.queryByText(/P50 warm reuse/)).toBeNull();
  });
  it('uses the live response directly and retains receipt, timing, constraints and fallback', async () => {
    view(); await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    expect(await screen.findByText(/Live candle/)).toBeVisible();
    expect(fetch).toHaveBeenCalledWith(`/api/observatory/search-strategies/compare?query=${encodeURIComponent(CANONICAL_ANNA_QUERY)}`, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByText('127 ms')).toBeVisible();
    expect(screen.getByText('not measured')).toBeVisible();
    expect(screen.getByText('comparison-test')).toBeVisible();
    expect(screen.getByText(/persisted to Aurora/)).toBeVisible();
    expect(screen.getByText(/Rerank unavailable. Fallback order: rrf/)).toBeVisible();
    expect(screen.getByText(/Price ceiling: \$100/)).toBeVisible();
    await userEvent.click(screen.getByText('Inspect the typed plan and enforced constraints'));
    expect(screen.getByText(/"price_max_usd": 100/)).toBeVisible();
  });
  it('shows keyword, vector and hybrid rows side by side in the order returned', async () => {
    const result = payload();
    const row = (strategy: string, name: string, productId: number) => ({
      strategy, observedMs: 3, modeledCostPerThousandUsd: 0, products: [{ productId, name }],
    });
    result.strategies = [
      row('keyword only', 'Keyword hit', 11),
      row('vector only', 'Vector hit', 12),
      row('hybrid (RRF)', 'Hybrid hit', 13),
      ...result.strategies,
    ] as typeof result.strategies;
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => result } as Response);
    view(); await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    const headings = (await screen.findAllByRole('heading', { level: 3 })).map(h => h.textContent);
    const compared = ['keyword only', 'vector only', 'hybrid (RRF)'];
    expect(headings.filter(heading => compared.includes(heading ?? ''))).toEqual(compared);
    expect(screen.getByRole('list', { name: 'keyword only product order' })).toHaveTextContent('Keyword hit');
    expect(screen.getByRole('list', { name: 'vector only product order' })).toHaveTextContent('Vector hit');
    expect(screen.getByRole('list', { name: 'hybrid (RRF) product order' })).toHaveTextContent('Hybrid hit');
  });
  it('never upgrades an unpersisted response into durable proof', async () => {
    const result = payload(); result.receipt.persisted = false;
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => result } as Response);
    view(); await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    expect(await screen.findByText(/not persisted. Do not treat this response as durable evidence/)).toBeVisible();
  });
  it('clears prior results if the next comparison fails', async () => {
    view(); await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    await screen.findByText(/Live candle/);
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 503 } as Response);
    await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503');
    expect(screen.queryByText(/Live candle/)).toBeNull();
  });
  it('leaves absent durations and receipt status unknown', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ query: 'q', strategies: [{ strategy: 'vector only', products: [] }] }) } as Response);
    view(); await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    await waitFor(() => expect(screen.getByText(/Durable evidence is unconfirmed/)).toBeVisible());
    expect(screen.getAllByText('Not reported')).toHaveLength(3);
    expect(screen.queryByText('0 ms')).toBeNull();
  });
});
