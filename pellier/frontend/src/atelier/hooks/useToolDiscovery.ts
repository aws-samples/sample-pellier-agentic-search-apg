/**
 * useToolDiscovery — Dedicated hook for pgvector tool discovery.
 *
 * Always calls the real POST /api/atelier/tools/discover endpoint.
 * Returns ranked results with cosine distances, timing, and the SQL used.
 *
 * Requirements: 9.2, 9.3, 16.3
 */

import { useState, useCallback, useRef } from 'react';
import type { ToolDiscoveryResult } from '../types';

export interface UseToolDiscoveryResult {
  results: ToolDiscoveryResult[];
  loading: boolean;
  error: string | null;
  durationMs: number;
  sql: string;
}

export function useToolDiscovery(): UseToolDiscoveryResult & {
  discover: (query: string, limit?: number) => Promise<void>;
} {
  const [results, setResults] = useState<ToolDiscoveryResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [sql, setSql] = useState('');

  const requestIdRef = useRef(0);

  const discover = useCallback(async (query: string, limit = 5) => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    const startTime = performance.now();

    try {
      const response = await fetch('/api/atelier/tools/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit }),
      });

      if (!response.ok) {
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
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const message =
          err instanceof Error ? err.message : 'An unknown error occurred';
        setError(message);
        setResults([]);
        setDurationMs(0);
        setSql('');
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  return { results, loading, error, durationMs, sql, discover };
}
