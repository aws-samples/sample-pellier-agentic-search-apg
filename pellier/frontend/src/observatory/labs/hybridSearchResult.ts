/**
 * The recorded result of one `search_products_hybrid` call, as a ranked view.
 *
 * The tool_audit row carries the exact arguments and the returned products,
 * each with its fused (RRF) score and, when the reranker ran, its rerank score.
 * This reads that structured row, never display text, and derives nothing it
 * cannot see: a missing score stays missing.
 *
 * What ordered the list depends on the recorded `search_method`
 * (services/planned_hybrid_retrieval.py): `hybrid+rerank` returns rerank order;
 * `hybrid` and `hybrid (rerank fallback to RRF order)` return fused RRF order.
 * A declared merchandising rule (services/agent_tools.py) can then promote a
 * product, and the result records it in `merchandising_rules_applied`. Each
 * movement is credited to the step that caused it.
 */

export interface HybridPlanField {
  /** The recorded field name, so the view maps straight back to the JSON. */
  field: string;
  value: string | null;
  /** The untruncated value, when `value` is shortened for display. */
  full?: string | null;
}

/** What produced the returned order, per the recorded search method. */
export type HybridOrdering = 'rerank' | 'rrf' | 'rrf-fallback' | 'unrecorded';

export const SEARCH_METHOD_ORDERING: Record<string, HybridOrdering> = {
  'hybrid+rerank': 'rerank',
  hybrid: 'rrf',
  'hybrid (rerank fallback to RRF order)': 'rrf-fallback',
};

/** One entry of the recorded `merchandising_rules_applied` list. */
export interface MerchandisingRule {
  ruleId: string | null;
  signal: string | null;
  product: string | null;
  /** Rank before the rule ran, as recorded. */
  fromRank: number | null;
  toRank: number | null;
  reason: string | null;
}

export interface HybridResultRow {
  productId: string | null;
  name: string;
  /** Position in the returned list. */
  final: number;
  rrfScore: number | null;
  /** Order among the shown products by fused score, 1 = highest. */
  rrfRank: number | null;
  rerankScore: number | null;
  /** Order among the shown products by rerank score, when rerank ordered them. */
  rerankRank: number | null;
  /** Places the reranker moved it, RRF rank to rerank rank; negative is down. */
  movedByRerank: number | null;
  /** The recorded rule that promoted this product, if one did. */
  merchandising: MerchandisingRule | null;
  price: number | null;
}

export interface HybridSearchView {
  plan: HybridPlanField[];
  rows: HybridResultRow[];
  /** The recorded `search_method` label, verbatim. */
  searchMethod: string | null;
  ordering: HybridOrdering;
  merchandising: MerchandisingRule[];
  /** True when a rule left the returned order different from the ranking order. */
  merchandisingReordered: boolean;
  /** Size of the fused candidate pool, when recorded. Shown ranks are not pool ranks. */
  poolSize: number | null;
  /** Size of the raw args and result as recorded, in characters of JSON. */
  rawCharacters: number;
}

type Json = Record<string, unknown>;

function asObject(value: unknown): Json | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Json) : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function display(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : null;
  return String(value);
}

function truncateId(value: unknown): string | null {
  const text = display(value);
  if (!text) return null;
  return text.length > 14 ? `${text.slice(0, 14)}…` : text;
}

/** 1-based order of each row by a score, highest first; rows without one get null. */
function rankBy(products: Json[], field: string): (number | null)[] {
  const order = products
    .map((product, index) => ({ index, score: asNumber(product[field]) }))
    .filter((entry): entry is { index: number; score: number } => entry.score !== null)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((entry) => entry.index);
  return products.map((_, index) => {
    const at = order.indexOf(index);
    return at === -1 ? null : at + 1;
  });
}

function parseRules(value: unknown): MerchandisingRule[] {
  if (!Array.isArray(value)) return [];
  return value.map(asObject).filter((rule): rule is Json => rule !== null).map((rule) => ({
    ruleId: display(rule.ruleId),
    signal: display(rule.signal),
    product: display(rule.product),
    fromRank: asNumber(rule.fromRank),
    toRank: asNumber(rule.toRank),
    reason: display(rule.reason),
  }));
}

/**
 * Parse one recorded tool row (`{ args, result }`).
 *
 * Returns null unless the result carries products with a fused or rerank
 * score, so other tools keep their existing details view.
 */
export function parseHybridSearchResult(row: Json): HybridSearchView | null {
  const args = asObject(row.args) ?? {};
  const result = asObject(row.result);
  const products = Array.isArray(result?.products) ? (result!.products as unknown[]) : [];
  const scored = products
    .map(asObject)
    .filter((product): product is Json => product !== null);
  const hasScores = scored.some(
    (product) => asNumber(product.rrf_score) !== null || asNumber(product.rerank_score) !== null,
  );
  if (!result || !hasScores) return null;

  const plan = asObject(result.search_plan) ?? {};
  const hard = asObject(plan.hard_constraints) ?? {};
  const searchMethod = display(result.search_method);
  const ordering: HybridOrdering = (searchMethod && SEARCH_METHOD_ORDERING[searchMethod]) || 'unrecorded';
  const merchandising = parseRules(result.merchandising_rules_applied);

  const rrfRanks = rankBy(scored, 'rrf_score');
  const rerankRanks = ordering === 'rerank' ? rankBy(scored, 'rerank_score') : scored.map(() => null);

  const rows = scored.map((product, index): HybridResultRow => {
    const name = display(product.name) ?? '—';
    const rrfRank = rrfRanks[index];
    const rerankRank = rerankRanks[index];
    return {
      productId: display(product.productId ?? product.product_id),
      name,
      final: index + 1,
      rrfScore: asNumber(product.rrf_score),
      rrfRank,
      rerankScore: asNumber(product.rerank_score),
      rerankRank,
      movedByRerank: rrfRank !== null && rerankRank !== null ? rrfRank - rerankRank : null,
      merchandising: merchandising.find((rule) => rule.product !== null && rule.product === name) ?? null,
      price: asNumber(product.price),
    };
  });

  // The order the ranking step produced, before any rule: rerank rank when the
  // reranker ordered the list, RRF rank when fused order did.
  const rankingOrder = (item: HybridResultRow) => (ordering === 'rerank' ? item.rerankRank : item.rrfRank);
  const merchandisingReordered = merchandising.length > 0 && rows.some((item) => {
    const ranked = rankingOrder(item);
    return ranked !== null && ranked !== item.final;
  });

  const relaxations = display(plan.relaxations);
  return {
    plan: [
      { field: 'search_method', value: searchMethod },
      { field: 'pool_size', value: display(result.pool_size) },
      { field: 'rerank_pool_k', value: display(result.rerank_pool_k ?? plan.rerank_pool_k) },
      { field: 'top_k', value: display(plan.top_k) },
      { field: 'categories', value: display(hard.categories) },
      { field: 'in_stock_only', value: display(hard.in_stock_only) },
      {
        field: 'constraints_applied_before_rerank',
        value: display(result.constraints_applied_before_rerank),
      },
      ...(relaxations ? [{ field: 'relaxations', value: relaxations }] : []),
      { field: 'turn_id', value: truncateId(args.turn_id), full: display(args.turn_id) },
    ],
    rows,
    searchMethod,
    ordering,
    merchandising,
    merchandisingReordered,
    poolSize: asNumber(result.pool_size),
    rawCharacters: JSON.stringify(row.args ?? {}).length + JSON.stringify(row.result ?? {}).length,
  };
}
