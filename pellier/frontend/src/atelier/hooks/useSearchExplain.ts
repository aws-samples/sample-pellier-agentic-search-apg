/**
 * useSearchExplain — runs one query through GET /api/atelier/search/explain
 * and returns every pipeline stage (EMBED → VECTOR → LEXICAL → FUSION →
 * RERANK) for the Atelier "Search" mechanism surface.
 *
 * Unlike useToolDiscovery, this hook has NO offline fallback: the whole
 * point of the surface is to show real per-stage SQL, real per-branch
 * ranks, and the real rerank reordering against the live Aurora catalog.
 * Fabricating those numbers offline would defeat the lesson, so when the
 * endpoint is unavailable we surface an honest error instead of inventing
 * a ranking. (The endpoint itself already degrades honestly on a Bedrock
 * rerank outage — it shows RRF order unchanged with n/a scores.)
 */

import { useState, useCallback, useRef } from 'react';
import type { SearchExplainResponse, SearchStage } from '../types';

export interface UseSearchExplainResult {
  stages: SearchStage[];
  params: SearchExplainResponse['params'] | null;
  query: string;
  loading: boolean;
  error: string | null;
  durationMs: number;
  explain: (query: string) => Promise<void>;
}

export function useSearchExplain(): UseSearchExplainResult {
  const [stages, setStages] = useState<SearchStage[]>([]);
  const [params, setParams] = useState<SearchExplainResponse['params'] | null>(
    null,
  );
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);

  const requestIdRef = useRef(0);

  const explain = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;

    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    const startTime = performance.now();

    try {
      const response = await fetch(
        `/api/atelier/search/explain?query=${encodeURIComponent(trimmed)}`,
      );

      if (!response.ok) {
        throw new Error(
          `Search explain failed: ${response.status} ${response.statusText}`,
        );
      }

      const json: SearchExplainResponse = await response.json();

      if (currentRequestId === requestIdRef.current) {
        setStages(json.stages ?? []);
        setParams(json.params ?? null);
        setQuery(json.query ?? trimmed);
        setDurationMs(Math.round(performance.now() - startTime));
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const message =
          err instanceof Error ? err.message : 'An unknown error occurred';
        setError(message);
        setStages([]);
        setParams(null);
        setDurationMs(0);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  return { stages, params, query, loading, error, durationMs, explain };
}
