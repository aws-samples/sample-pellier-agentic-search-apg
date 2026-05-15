/**
 * useToolDiscovery — Dedicated hook for pgvector tool discovery.
 *
 * Always calls the real POST /api/atelier/tools/discover endpoint.
 * Returns ranked results with cosine distances, timing, and the SQL used.
 *
 * Requirements: 9.2, 9.3, 16.3
 */

import { useState, useCallback, useRef } from 'react';
import type { Tool, ToolDiscoveryResult } from '../types';
import {
  discoverToolsLocally,
  OFFLINE_DISCOVERY_SQL,
} from '../surfaces/understand/toolsDiscoveryUtils';

export interface UseToolDiscoveryResult {
  results: ToolDiscoveryResult[];
  loading: boolean;
  error: string | null;
  durationMs: number;
  sql: string;
}

export function useToolDiscovery(catalog?: Tool[]): UseToolDiscoveryResult & {
  discover: (query: string, limit?: number) => Promise<void>;
  usedOfflineFallback: boolean;
} {
  const [results, setResults] = useState<ToolDiscoveryResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [sql, setSql] = useState('');
  const [usedOfflineFallback, setUsedOfflineFallback] = useState(false);

  const requestIdRef = useRef(0);

  const applyOfflineFallback = useCallback(
    (query: string, limit: number, elapsed: number) => {
      if (!catalog?.length) return false;
      setResults(discoverToolsLocally(query, catalog, limit));
      setDurationMs(elapsed);
      setSql(OFFLINE_DISCOVERY_SQL.replace('$1', String(limit)));
      setUsedOfflineFallback(true);
      setError(null);
      return true;
    },
    [catalog],
  );

  const discover = useCallback(async (query: string, limit = 5) => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    setUsedOfflineFallback(false);

    const startTime = performance.now();

    try {
      const response = await fetch('/api/atelier/tools/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit }),
      });

      if (!response.ok) {
        const elapsed = Math.round(performance.now() - startTime);
        if (
          currentRequestId === requestIdRef.current &&
          applyOfflineFallback(query, limit, elapsed)
        ) {
          return;
        }
        throw new Error(
          `Discovery request failed: ${response.status} ${response.statusText}`,
        );
      }

      const json = await response.json();

      if (currentRequestId === requestIdRef.current) {
        const elapsed = Math.round(performance.now() - startTime);
        setResults(json.results ?? json.rows ?? []);
        setDurationMs(json.duration_ms ?? elapsed);
        setSql(
          json.sql ??
            `SELECT name, description, 1 - (embedding <=> query_embedding) AS similarity\nFROM tool_registry\nORDER BY embedding <=> query_embedding\nLIMIT ${limit};`,
        );
        setUsedOfflineFallback(false);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const elapsed = Math.round(performance.now() - startTime);
        if (applyOfflineFallback(query, limit, elapsed)) {
          return;
        }
        const message =
          err instanceof Error ? err.message : 'An unknown error occurred';
        setError(message);
        setResults([]);
        setDurationMs(0);
        setSql('');
        setUsedOfflineFallback(false);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [applyOfflineFallback]);

  return { results, loading, error, durationMs, sql, discover, usedOfflineFallback };
}
