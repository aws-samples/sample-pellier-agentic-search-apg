/**
 * Atelier Observatory — Central data-fetching hook
 *
 * Abstracts fixture vs. API data loading for all Atelier surfaces.
 * In fixture mode (default), dynamically imports from /fixtures/ based on key.
 * In API mode, fetches from /api/atelier/* endpoints with transparent fallback
 * to fixture data when the API is unavailable.
 *
 * Requirements: 16.1, 16.2, 16.4, 16.5
 */

import { useState, useEffect, useCallback, useRef } from 'react';

type DataSource = 'fixture' | 'api';

export interface UseAtelierDataOptions {
  key: string;
  params?: Record<string, string>;
  source?: DataSource;
}

export interface UseAtelierDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Map of fixture keys to their dynamic import functions.
 * Each key corresponds to a JSON file in /fixtures/.
 */
const fixtureImporters: Record<string, () => Promise<{ default: unknown }>> = {
  sessions: () => import('../fixtures/sessions.json'),
  // Legacy session detail fixture — kept while older test code still
  // references session-7f5a. New fixtures live under the canonical
  // session IDs from sessions.json.
  'session-7f5a': () => import('../fixtures/session-7f5a.json'),
  // Marco's canonical workshop arc — three session-detail fixtures.
  // See lab-content/shared/marco-arc-overview.en.md.
  'session-marco-opening-demo': () => import('../fixtures/session-marco-opening-demo.json'),
  'session-marco-midpoint-checkpoint': () => import('../fixtures/session-marco-midpoint-checkpoint.json'),
  'session-marco-capstone': () => import('../fixtures/session-marco-capstone.json'),
  // Supporting personas — evidence of range, no instructional checkpoints.
  'session-anna-birthday-gift': () => import('../fixtures/session-anna-birthday-gift.json'),
  'session-anna-housewarming': () => import('../fixtures/session-anna-housewarming.json'),
  'session-theo-pour-over': () => import('../fixtures/session-theo-pour-over.json'),
  'session-theo-ceramics-return': () => import('../fixtures/session-theo-ceramics-return.json'),
  agents: () => import('../fixtures/agents.json'),
  tools: () => import('../fixtures/tools.json'),
  routing: () => import('../fixtures/routing.json'),
  'memory-marco': () => import('../fixtures/memory-marco.json'),
  performance: () => import('../fixtures/performance.json'),
  evaluations: () => import('../fixtures/evaluations.json'),
  observatory: () => import('../fixtures/observatory.json'),
  architecture: () => import('../fixtures/architecture.json'),
};

/**
 * Map of data keys to their API endpoint paths.
 */
const apiEndpoints: Record<string, string> = {
  sessions: '/api/atelier/sessions',
  agents: '/api/atelier/agents',
  tools: '/api/atelier/tools',
  routing: '/api/atelier/routing',
  performance: '/api/atelier/performance',
  evaluations: '/api/atelier/evaluations',
  observatory: '/api/atelier/observatory',
  architecture: '/api/atelier/architecture',
};

/**
 * Build the API URL for a given key and optional params.
 */
function buildApiUrl(key: string, params?: Record<string, string>): string {
  // Handle parameterized keys like "session-{id}" or "memory-{persona}"
  if (key.startsWith('session-') && key !== 'sessions') {
    const id = key.replace('session-', '');
    return `/api/atelier/sessions/${id}`;
  }
  if (key.startsWith('memory-')) {
    const persona = key.replace('memory-', '');
    return `/api/atelier/memory/${persona}`;
  }

  const base = apiEndpoints[key];
  if (!base) return `/api/atelier/${key}`;

  if (params) {
    const searchParams = new URLSearchParams(params);
    return `${base}?${searchParams.toString()}`;
  }
  return base;
}

export function useAtelierData<T = unknown>(
  options: UseAtelierDataOptions,
): UseAtelierDataResult<T> {
  const { key, params, source = 'fixture' } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track the current request to avoid stale updates
  const requestIdRef = useRef(0);

  const fetchData = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    try {
      if (source === 'fixture') {
        const importer = fixtureImporters[key];
        if (!importer) {
          throw new Error(`No fixture found for key: "${key}"`);
        }
        const module = await importer();
        if (currentRequestId === requestIdRef.current) {
          setData(module.default as T);
        }
      } else {
        // API mode with transparent fallback to fixtures
        try {
          const url = buildApiUrl(key, params);
          const response = await fetch(url);

          if (!response.ok) {
            throw new Error(
              `API request failed: ${response.status} ${response.statusText}`,
            );
          }

          const json = await response.json();
          if (currentRequestId === requestIdRef.current) {
            setData(json as T);
          }
        } catch {
          // API failed — transparently fall back to fixture data
          const importer = fixtureImporters[key];
          if (importer) {
            try {
              const module = await importer();
              if (currentRequestId === requestIdRef.current) {
                setData(module.default as T);
              }
            } catch (fixtureErr) {
              // Both API and fixture fallback failed
              if (currentRequestId === requestIdRef.current) {
                const message =
                  fixtureErr instanceof Error
                    ? fixtureErr.message
                    : 'An unknown error occurred';
                setError(message);
                setData(null);
              }
            }
          } else {
            // No fixture available for this key — surface the original API error
            if (currentRequestId === requestIdRef.current) {
              setError(`API unavailable and no fixture fallback for key: "${key}"`);
              setData(null);
            }
          }
        }
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const message =
          err instanceof Error ? err.message : 'An unknown error occurred';
        setError(message);
        setData(null);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [key, params, source]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}
