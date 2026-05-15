import { describe, expect, it } from 'vitest';
import {
  EVALUATION_METRICS,
  filterMetricsByTier,
} from './evalMetrics';

describe('evalMetrics', () => {
  it('includes core retrieval metrics', () => {
    const ids = EVALUATION_METRICS.map((m) => m.id);
    expect(ids).toContain('recall-at-k');
    expect(ids).toContain('mrr');
    expect(ids).toContain('context-relevance');
  });

  it('filters by tier', () => {
    const retrieval = filterMetricsByTier(EVALUATION_METRICS, 'retrieval');
    expect(retrieval.length).toBeGreaterThanOrEqual(4);
    expect(retrieval.every((m) => m.tier === 'retrieval')).toBe(true);
  });
});
