/**
 * Atelier Observatory — Performance types
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
  /**
   * Anna's anchor capability comparison: vector-only vs hybrid (RRF) vs
   * hybrid+rerank, measured against the live catalog. Numbers come from
   * /api/atelier/search-strategies/compare when a query is supplied;
   * the fixture below seeds reasonable defaults so the card always
   * renders.
   *
   * Cost notes: vector + hybrid run entirely against Aurora and are
   * effectively free per query (already-paid-for compute). Rerank
   * adds a Bedrock invoke_model call to Cohere Rerank v3.5 at
   * roughly $1 per 1000 queries — the workshop's "is the lift
   * worth it?" question has a real answer for participants to
   * weigh against the recall@5 delta.
   */
  searchStrategies: {
    strategy: 'vector only' | 'hybrid (RRF)' | 'hybrid + rerank';
    recallAt5: number;       // 0.0–1.0
    p50Ms: number;            // wall-clock median
    costPerThousandUsd: number;
    isShipped: boolean;       // true for Anna's path (hybrid+rerank)
    products?: { name: string; productId: number }[]; // top-5 when live
  }[];
  storageUsage: {
    label: string;
    sizeBytes: number;
    percentage: number;
  }[];
}
