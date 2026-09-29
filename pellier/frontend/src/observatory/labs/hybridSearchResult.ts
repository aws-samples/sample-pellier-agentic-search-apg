/**
 * The recorded result of one `search_products_hybrid` call, as a ranked view.
 *
 * The tool_audit row carries the exact arguments and the returned products,
 * each with its fused (RRF) score and its rerank score. Printed as JSON that is
 * a 760px block with the answer to "why is this product second?" buried in it.
 * This reads the same structured row the backend returns, never display text,
 * and derives nothing it cannot see: a missing score stays missing.
 */

export interface HybridPlanField {
  /** The recorded field name, so the view maps straight back to the JSON. */
  field: string;
  value: string | null;
  /** The untruncated value, when `value` is shortened for display. */
  full?: string | null;
}

export interface HybridResultRow {
  productId: string | null;
  name: string;
  /** Position in the returned list, which is the order after rerank. */
  final: number;
  rrfScore: number | null;
  /** Order among the returned products by fused score, 1 = highest. */
  rrfRank: number | null;
  rerankScore: number | null;
  /** Places gained from RRF order to final order; negative means it dropped. */
  moved: number | null;
  price: number | null;
}

export interface HybridSearchView {
  plan: HybridPlanField[];
  rows: HybridResultRow[];
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

  const byRrf = scored
    .map((product, index) => ({ index, score: asNumber(product.rrf_score) }))
    .filter((entry): entry is { index: number; score: number } => entry.score !== null)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.index);

  const rows = scored.map((product, index): HybridResultRow => {
    const rankIndex = byRrf.indexOf(index);
    const rrfRank = rankIndex === -1 ? null : rankIndex + 1;
    return {
      productId: display(product.productId ?? product.product_id),
      name: display(product.name) ?? '—',
      final: index + 1,
      rrfScore: asNumber(product.rrf_score),
      rrfRank,
      rerankScore: asNumber(product.rerank_score),
      moved: rrfRank === null ? null : rrfRank - (index + 1),
      price: asNumber(product.price),
    };
  });

  return {
    plan: [
      { field: 'search_method', value: display(result.search_method ?? plan.retrieval_strategy) },
      { field: 'pool_size', value: display(result.pool_size) },
      { field: 'rerank_pool_k', value: display(result.rerank_pool_k ?? plan.rerank_pool_k) },
      { field: 'top_k', value: display(plan.top_k) },
      { field: 'categories', value: display(hard.categories) },
      { field: 'in_stock_only', value: display(hard.in_stock_only) },
      {
        field: 'constraints_applied_before_rerank',
        value: display(result.constraints_applied_before_rerank),
      },
      { field: 'turn_id', value: truncateId(args.turn_id), full: display(args.turn_id) },
    ],
    rows,
    poolSize: asNumber(result.pool_size),
    rawCharacters: JSON.stringify(row.args ?? {}).length + JSON.stringify(row.result ?? {}).length,
  };
}
