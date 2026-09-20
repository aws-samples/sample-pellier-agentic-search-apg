/**
 * Pellier Observatory — live data-fetching hook.
 *
 * Participant-facing panels read their state from the API. A failed request is
 * rendered as an explicit unavailable state; it is never substituted with a
 * browser fixture that could be mistaken for an Aurora result.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useOptionalAuth } from '../../contexts/AuthContext';

export interface UseObservatoryDataOptions {
  key: string;
  params?: Record<string, string>;
}

export interface UseObservatoryDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  errorStatus?: number | null;
  refetch: () => void;
}

const apiEndpoints: Record<string, string> = {
  sessions: '/api/observatory/sessions',
  agents: '/api/observatory/agents',
  tools: '/api/observatory/tools/list',
  routing: '/api/observatory/routing',
  skills: '/api/observatory/skills',
  performance: '/api/observatory/performance',
  evaluations: '/api/observatory/evaluations',
  architecture: '/api/observatory/architecture',
  'production-patterns': '/api/observatory/production-patterns',
};

function buildApiUrl(key: string, params?: Record<string, string>): string {
  if (key.startsWith('session-') && key !== 'sessions') {
    return `/api/observatory/sessions/${key.replace('session-', '')}`;
  }
  if (key.startsWith('memory-showcase-')) {
    return `/api/observatory/memory-showcase/${key.replace('memory-showcase-', '')}`;
  }
  if (key.startsWith('memory-')) {
    return `/api/observatory/memory/${key.replace('memory-', '')}`;
  }

  const base = apiEndpoints[key] ?? `/api/observatory/${key}`;
  if (!params || Object.keys(params).length === 0) return base;
  return `${base}?${new URLSearchParams(params).toString()}`;
}

export function useObservatoryData<T = unknown>(
  options: UseObservatoryDataOptions,
): UseObservatoryDataResult<T> {
  const { key, params } = options;
  const principal = useOptionalAuth()?.user?.sub ?? '';
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [settledKey, setSettledKey] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const paramsKey = JSON.stringify(params ?? {});
  const requestKey = JSON.stringify([key, paramsKey, principal]);

  const fetchData = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    setData(null);
    let status: number | null = null;

    try {
      const response = await fetch(buildApiUrl(key, params));
      if (!response.ok) {
        status = response.status;
        // 404 is "this specific record does not exist" (a stale link, a
        // mistyped id), never "the evidence service is down" -- collapsing
        // it into the same "temporarily unavailable, try again" message as
        // a 500/503 tells a participant retrying will help when it never
        // will. `errorStatus` already carries the real code for a caller
        // (e.g. SessionView) that wants to render a dedicated not-found
        // state instead of a retry affordance.
        throw new Error(status === 401
          ? 'Sign in to read your account’s evidence.'
          : status === 403
            ? 'This profile belongs to a different account. Choose the profile that matches your sign-in.'
            : status === 404
              ? 'This evidence could not be found.'
              : 'This evidence is temporarily unavailable. Please try again.');
      }
      const payload = await response.json();
      if (requestId === requestIdRef.current) {
        setData(payload as T);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setData(null);
        setErrorStatus(status);
        setError(
          err instanceof Error ? err.message : 'Live data request failed',
        );
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setSettledKey(requestKey);
      }
    }
    // `paramsKey` supplies a stable dependency for object-shaped query params.
  }, [key, paramsKey, principal]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const current = settledKey === requestKey;
  return {
    data: current ? data : null,
    loading: !current || loading,
    error: current ? error : null,
    errorStatus: current ? errorStatus : null,
    refetch: fetchData,
  };
}
