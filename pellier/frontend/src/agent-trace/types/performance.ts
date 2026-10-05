/**
 * Pellier Labs Observatory — Performance types
 *
 * Metrics, histograms, latency budgets, pgvector comparisons, and storage usage.
 *
 * Requirements: 16.5
 */

export interface PerformanceData {
  coldStartP50: number;
  warmReuseP50: number;
  sampleCount: number;
  histogram: { bucket: string; count: number; type: 'cold' | 'warm' }[];
  latencyBudget: {
    panel: string;
    type: 'llm' | 'tool' | 'memory';
    p50Ms: number;
    maxMs: number;
  }[];
  pgvectorComparison: {
    strategy: string;
    recall: number;
    qps: number;
    buildTime: string;
    storage: string;
    isShipped: boolean;
  }[];
  pgvectorTuning: {
    capability: string;
    knob: string;
    productionUse: string;
    smokeResult: string;
    tradeoff: string;
    status: 'enabled' | 'available';
  }[];
  /**
   * Anna's anchor capability comparison: four retrieval strategies
   * measured against the live catalog. Numbers come from
   * /api/agent-trace/search-strategies/compare when a query is supplied;
   * the fixture below seeds reasonable defaults so the card always
   * renders.
   *
   * Strategies:
   *   1. vector only            — pgvector cosine, no lexical signal
   *   2. hybrid (RRF)           — pgvector + Postgres FTS via reciprocal rank fusion (teaching foil)
   *   3. hybrid + rerank        — RRF candidates rescored by Cohere Rerank v3.5
   *   4. agentic                — Sonnet 5 extracts {categories, tags, price_max_usd, in_stock_only,
   *                               soft_signal} → filtered HNSW with iterative_scan → rerank against
   *                               soft_signal (Anna's path)
   *
   * Cost notes: vector + hybrid run against Aurora after a shared query
   * embedding. Rerank
   * adds a Bedrock invoke_model call to Cohere Rerank v3.5. Agentic
   * adds one Sonnet 5 structured-extraction call on top of rerank;
   * the workshop's "is the lift worth it?" question has a real answer
   * for participants to weigh against the recall@5 + filter-respect
   * deltas.
   */
  searchStrategies: {
    strategy: 'vector only' | 'hybrid (RRF)' | 'hybrid + rerank' | 'agentic (Sonnet → filter → vector → rerank)';
    recallAt5: number;       // 0.0–1.0
    modeledLatencyMs: number;
    observedMs?: number;     // one live endpoint observation, not a percentile
    modeledCostPerThousandUsd: number;
    isShipped: boolean;       // true for Anna's path (agentic)
    rerankExecuted?: boolean;
    productOrderSource?: string;
    degradedReason?: string | null;
    costComponents?: string[];
    products?: { name: string; productId: number }[]; // top-5 when live
    /**
     * Only populated for the agentic strategy when live. Surfaces what
     * Sonnet extracted and which filter-degradation step was used so
     * participants can see the structured signal that drove the WHERE
     * clause and the residual taste phrase the reranker scored against.
     */
    extractedFilters?: {
      categories: string[];
      tags: string[];
      priceMaxUsd: number | null;
      inStockOnly: boolean;
      softSignal: string;
      filterUsed: 'strict' | 'drop_tags' | 'drop_cats' | 'drop_all';
      hardConstraintsEnforced?: boolean;
    };
  }[];
  storageUsage: {
    label: string;
    sizeBytes: number;
    percentage: number;
  }[];
}
