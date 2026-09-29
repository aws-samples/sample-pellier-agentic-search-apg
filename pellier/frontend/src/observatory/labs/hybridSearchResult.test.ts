import { describe, expect, it } from 'vitest';
import { parseHybridSearchResult } from './hybridSearchResult';

// Shape of a recorded search_products_hybrid tool_audit row (Theo's ceramics
// turn), trimmed to the fields the view reads.
const recorded = {
  args: { query: 'hand-thrown ceramics', turn_id: 'turn-d224e15a874145eebe8545ca10be82f2', category: 'Home Decor' },
  result: {
    status: 'success',
    pool_size: 21,
    rerank_pool_k: 30,
    search_method: 'hybrid+rerank',
    constraints_applied_before_rerank: true,
    search_plan: { top_k: 5, hard_constraints: { categories: ['Home Decor'], in_stock_only: false } },
    products: [
      { productId: '31', name: 'Stoneware Pour-Over Set', price: 165, rrf_score: 0.03279, rerank_score: 0.797 },
      { productId: '44', name: 'Olive Branch Vessel', price: 185, rrf_score: 0.03008, rerank_score: 0.286 },
      { productId: '12', name: 'Ceramic Tumblers', price: 78, rrf_score: 0.03226, rerank_score: 0.231 },
      { productId: '9', name: 'Ceramic Ring Dish', price: 35, rrf_score: 0.03102, rerank_score: 0.188 },
      { productId: '7', name: 'Linen Runner', price: 90, rrf_score: 0.03175, rerank_score: 0.101 },
    ],
  },
};

describe('recorded hybrid search result', () => {
  it('orders products by fused score and says how far rerank moved each one', () => {
    const view = parseHybridSearchResult(recorded)!;
    const olive = view.rows[1];
    expect(olive).toMatchObject({ name: 'Olive Branch Vessel', final: 2, rrfRank: 5, moved: 3 });
    expect(view.rows[0]).toMatchObject({ final: 1, rrfRank: 1, moved: 0 });
    expect(view.rows[2]).toMatchObject({ final: 3, rrfRank: 2, moved: -1 });
    expect(view.poolSize).toBe(21);
  });

  it('reports the plan by its recorded field names', () => {
    const plan = Object.fromEntries(parseHybridSearchResult(recorded)!.plan.map((f) => [f.field, f]));
    expect(plan.search_method.value).toBe('hybrid+rerank');
    expect(plan.categories.value).toBe('Home Decor');
    expect(plan.in_stock_only.value).toBe('false');
    expect(plan.constraints_applied_before_rerank.value).toBe('true');
    expect(plan.turn_id.value).toBe('turn-d224e15a8…');
    expect(plan.turn_id.full).toBe('turn-d224e15a874145eebe8545ca10be82f2');
  });

  it('leaves a missing score missing instead of inventing a rank', () => {
    const view = parseHybridSearchResult({
      args: {},
      result: { products: [
        { name: 'Scored', rrf_score: 0.02, rerank_score: 0.5 },
        { name: 'Unscored', rerank_score: 0.4 },
      ] },
    })!;
    expect(view.rows[1]).toMatchObject({ rrfScore: null, rrfRank: null, moved: null, price: null });
    expect(view.plan.find((f) => f.field === 'pool_size')?.value).toBeNull();
    expect(view.poolSize).toBeNull();
  });

  it('declines results that carry no retrieval scores', () => {
    expect(parseHybridSearchResult({ args: {}, result: { count: 1, products: [{ name: 'Bowl', price: 40 }] } })).toBeNull();
    expect(parseHybridSearchResult({ args: {}, result: { tool: 'initiate_return', error: 'managed_rail_required' } })).toBeNull();
    expect(parseHybridSearchResult({ args: {}, result: 'not an object' })).toBeNull();
  });
});
