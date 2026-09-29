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
    search_plan: { top_k: 5, relaxations: [], hard_constraints: { categories: ['Home Decor'], in_stock_only: false } },
    products: [
      { productId: '31', name: 'Stoneware Pour-Over Set', price: 165, rrf_score: 0.03279, rerank_score: 0.797 },
      { productId: '44', name: 'Olive Branch Vessel', price: 185, rrf_score: 0.03008, rerank_score: 0.286 },
      { productId: '12', name: 'Ceramic Tumblers', price: 78, rrf_score: 0.03226, rerank_score: 0.231 },
      { productId: '9', name: 'Ceramic Ring Dish', price: 35, rrf_score: 0.03102, rerank_score: 0.188 },
      { productId: '7', name: 'Linen Runner', price: 90, rrf_score: 0.03175, rerank_score: 0.101 },
    ],
  },
};

// tool_audit 314: Anna's housewarming turn. Rerank put Olive Branch Vessel
// second; the declared rule then promoted it to first.
const merchandised = {
  args: { query: 'housewarming gift slow morning ritual ceramic pour-over coffee', turn_id: 'turn-5011ef8fbb554291a86da6d9245155e3' },
  result: {
    pool_size: 21,
    rerank_pool_k: 30,
    search_method: 'hybrid+rerank',
    merchandising_rules_applied: [{
      ruleId: 'merch.milestone-home-gift.v1',
      signal: 'curated_hero',
      product: 'Olive Branch Vessel',
      fromRank: 2,
      toRank: 1,
      reason: 'Declared merchandising rule: curated housewarming hero promoted above pure relevance order.',
    }],
    products: [
      { productId: '44', name: 'Olive Branch Vessel', price: 185, rrf_score: 0.03055037313432836, rerank_score: 0.21842791140079496 },
      { productId: '31', name: 'Stoneware Pour-Over Set', price: 165, rrf_score: 0.03278688524590164, rerank_score: 0.542015552520752 },
      { productId: '12', name: 'Ceramic Tumblers', price: 78, rrf_score: 0.03200204813108039, rerank_score: 0.1102125272154808 },
      { productId: '19', name: 'Wabi-Sabi Bowl', price: 65, rrf_score: 0.03125763125763126, rerank_score: 0.05436427518725395 },
      { productId: '52', name: 'Blown Glass Decanter', price: 210, rrf_score: 0.025978407557354925, rerank_score: 0.05171611160039902 },
    ],
  },
};

// services/planned_hybrid_retrieval.py: `hybrid` returns RRF order with
// rerank_score None; the fallback label means the reranker returned nothing.
const withoutRerank = (searchMethod: string) => ({
  args: {},
  result: {
    pool_size: 12,
    search_method: searchMethod,
    products: [
      { name: 'First by RRF', rrf_score: 0.033, rerank_score: null, price: 40 },
      { name: 'Second by RRF', rrf_score: 0.031, rerank_score: null, price: 55 },
    ],
  },
});

describe('recorded hybrid search result', () => {
  it('credits rerank with the move from RRF order to rerank order', () => {
    const view = parseHybridSearchResult(recorded)!;
    expect(view.ordering).toBe('rerank');
    const olive = view.rows[1];
    expect(olive).toMatchObject({ name: 'Olive Branch Vessel', final: 2, rrfRank: 5, rerankRank: 2, movedByRerank: 3, merchandising: null });
    expect(view.rows[0]).toMatchObject({ final: 1, rrfRank: 1, rerankRank: 1, movedByRerank: 0 });
    expect(view.rows[2]).toMatchObject({ final: 3, rrfRank: 2, movedByRerank: -1 });
    expect(view.merchandisingReordered).toBe(false);
    expect(view.poolSize).toBe(21);
  });

  it('credits a declared merchandising rule, not rerank, with the promotion', () => {
    const view = parseHybridSearchResult(merchandised)!;
    expect(view.ordering).toBe('rerank');
    expect(view.merchandisingReordered).toBe(true);
    expect(view.merchandising).toEqual([expect.objectContaining({ ruleId: 'merch.milestone-home-gift.v1', product: 'Olive Branch Vessel', fromRank: 2, toRank: 1 })]);
    const olive = view.rows[0];
    // RRF put it fourth, rerank second: rerank moved it two places. The rule,
    // not rerank, took it from second to first.
    expect(olive).toMatchObject({ final: 1, rrfRank: 4, rerankRank: 2, movedByRerank: 2 });
    expect(olive.merchandising?.ruleId).toBe('merch.milestone-home-gift.v1');
    // The reranker's winner is second only because of the rule.
    expect(view.rows[1]).toMatchObject({ name: 'Stoneware Pour-Over Set', final: 2, rerankRank: 1, movedByRerank: 0, merchandising: null });
  });

  it.each([
    ['hybrid', 'rrf'],
    ['hybrid (rerank fallback to RRF order)', 'rrf-fallback'],
  ])('reads %s as fused RRF order with no rerank movement', (method, ordering) => {
    const view = parseHybridSearchResult(withoutRerank(method))!;
    expect(view.ordering).toBe(ordering);
    expect(view.searchMethod).toBe(method);
    for (const row of view.rows) expect(row).toMatchObject({ rerankScore: null, rerankRank: null, movedByRerank: null });
    expect(view.rows.map((row) => row.rrfRank)).toEqual([1, 2]);
  });

  it('does not name an ordering the record does not state', () => {
    const view = parseHybridSearchResult({ args: {}, result: { products: [{ name: 'A', rrf_score: 0.02, rerank_score: 0.4 }] } })!;
    expect(view.ordering).toBe('unrecorded');
    expect(view.searchMethod).toBeNull();
    expect(view.rows[0]).toMatchObject({ rerankRank: null, movedByRerank: null });
    const method = parseHybridSearchResult({ args: {}, result: { search_method: 'vector', products: [{ name: 'A', rrf_score: 0.02 }] } })!;
    expect(method.ordering).toBe('unrecorded');
  });

  it('reports the plan by its recorded field names', () => {
    const plan = Object.fromEntries(parseHybridSearchResult(recorded)!.plan.map((f) => [f.field, f]));
    expect(plan.search_method.value).toBe('hybrid+rerank');
    expect(plan.categories.value).toBe('Home Decor');
    expect(plan.in_stock_only.value).toBe('false');
    expect(plan.constraints_applied_before_rerank.value).toBe('true');
    expect(plan.turn_id.value).toBe('turn-d224e15a8…');
    expect(plan.turn_id.full).toBe('turn-d224e15a874145eebe8545ca10be82f2');
    // An empty relaxation list is not a relaxation.
    expect(plan.relaxations).toBeUndefined();
    const relaxed = parseHybridSearchResult({ ...recorded, result: { ...recorded.result, search_plan: { relaxations: ['drop_tags'] } } })!;
    expect(relaxed.plan.find((f) => f.field === 'relaxations')?.value).toBe('drop_tags');
  });

  it('never takes the search method from the plan’s requested strategy', () => {
    const view = parseHybridSearchResult({ args: {}, result: { search_plan: { retrieval_strategy: 'hybrid_rerank' }, products: [{ name: 'A', rrf_score: 0.02 }] } })!;
    expect(view.plan.find((f) => f.field === 'search_method')?.value).toBeNull();
  });

  it('leaves a missing score missing instead of inventing a rank', () => {
    const view = parseHybridSearchResult({
      args: {},
      result: { search_method: 'hybrid+rerank', products: [
        { name: 'Scored', rrf_score: 0.02, rerank_score: 0.5 },
        { name: 'Unscored', rerank_score: 0.4 },
      ] },
    })!;
    expect(view.rows[1]).toMatchObject({ rrfScore: null, rrfRank: null, movedByRerank: null, price: null });
    expect(view.plan.find((f) => f.field === 'pool_size')?.value).toBeNull();
    expect(view.poolSize).toBeNull();
  });

  it('declines results that carry no retrieval scores', () => {
    expect(parseHybridSearchResult({ args: {}, result: { count: 1, products: [{ name: 'Bowl', price: 40 }] } })).toBeNull();
    expect(parseHybridSearchResult({ args: {}, result: { tool: 'initiate_return', error: 'managed_rail_required' } })).toBeNull();
    expect(parseHybridSearchResult({ args: {}, result: 'not an object' })).toBeNull();
  });
});
