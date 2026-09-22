import { apiFetch } from '../../services/apiBase'
/**
 * useBuildState — Determines shipped vs exercise status for tools and agents.
 *
 * Two sources, in precedence order:
 *   1. GET /api/observatory/build-state — authoritative. Merges overlays: when
 *      each Lab 1 scaffold is complete, promotes the Inventory Agent definition
 *      and check_inventory tool independently without editing JSON fixtures.
 *   2. Fixture data (agents.json / tools.json) — used when the endpoint is
 *      unreachable. Callers must treat a zero total as "unknown" rather than
 *      substituting a hardcoded count; see the Sidebar badges.
 *
 * Consumers (Agents, Tools surfaces, WorkshopProgressStrip) use this hook
 * to get the canonical status of each item. When an item transitions from
 * exercise → shipped, the UI updates automatically (dashed → solid styling).
 *
 * Requirements: 17.1, 17.2, 17.3
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useObservatoryData } from './useObservatoryData';
import type { Agent } from '../types/agent';
import type { Tool } from '../types/tool';

/* -----------------------------------------------------------------------
 * Types
 * ----------------------------------------------------------------------- */

export type BuildStatus = 'shipped' | 'exercise';

export interface BuildStateResult {
  /** Status map keyed by agent name → shipped | exercise */
  agentStatus: Record<string, BuildStatus>;
  /** Status map keyed by tool functionName → shipped | exercise */
  toolStatus: Record<string, BuildStatus>;
  /** Shipped agent count */
  agentShipped: number;
  /** Total agent count */
  agentTotal: number;
  /** Shipped tool count */
  toolShipped: number;
  /** Total tool count */
  toolTotal: number;
  /** Whether the build state is still loading */
  loading: boolean;
  /** Re-check build state (e.g., after a file change) */
  refresh: () => void;
}

/* -----------------------------------------------------------------------
 * API response shape (for future backend endpoint)
 * ----------------------------------------------------------------------- */

interface BuildStateApiResponse {
  agents: Record<string, BuildStatus>;
  tools: Record<string, BuildStatus>;
}

/* -----------------------------------------------------------------------
 * Hook implementation
 * ----------------------------------------------------------------------- */

export function useBuildState(): BuildStateResult {
  const { data: agents, loading: agentsLoading } = useObservatoryData<Agent[]>({
    key: 'agents',
  });
  const { data: tools, loading: toolsLoading } = useObservatoryData<Tool[]>({
    key: 'tools',
  });

  const [apiOverrides, setApiOverrides] = useState<BuildStateApiResponse | null>(null);
  const [apiLoading, setApiLoading] = useState(false);
  const requestIdRef = useRef(0);

  /**
   * Attempt to fetch build state from the backend.
   * Falls back silently to fixture data if the endpoint is unavailable.
   */
  const fetchBuildState = useCallback(async () => {
    const currentId = ++requestIdRef.current;
    setApiLoading(true);

    try {
      const res = await apiFetch('/api/observatory/build-state');
      if (!res.ok) {
        // Backend doesn't have this endpoint yet — that's fine, use fixtures
        if (currentId === requestIdRef.current) {
          setApiOverrides(null);
        }
        return;
      }
      const data: BuildStateApiResponse = await res.json();
      if (currentId === requestIdRef.current) {
        setApiOverrides(data);
      }
    } catch {
      // Network error or endpoint not available — silently fall back to fixtures
      if (currentId === requestIdRef.current) {
        setApiOverrides(null);
      }
    } finally {
      if (currentId === requestIdRef.current) {
        setApiLoading(false);
      }
    }
  }, []);

  // Try the API on mount (non-blocking — fixture data is the fallback)
  useEffect(() => {
    fetchBuildState();
  }, [fetchBuildState]);

  // After completing either Lab 1 scaffold, revisit the tab or focus the
  // window so build-state re-fetches once uvicorn has reloaded.
  useEffect(() => {
    const refetchBuildState = () => {
      fetchBuildState();
    };
    const onVisibility = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        fetchBuildState();
      }
    };
    window.addEventListener('focus', refetchBuildState);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('focus', refetchBuildState);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [fetchBuildState]);

  /* -----------------------------------------------------------------------
   * Derive status maps
   * ----------------------------------------------------------------------- */

  const agentStatus: Record<string, BuildStatus> = {};
  const toolStatus: Record<string, BuildStatus> = {};

  // Start with fixture data
  if (agents) {
    for (const agent of agents) {
      agentStatus[agent.name] = agent.status;
    }
  }
  if (tools) {
    for (const tool of tools) {
      toolStatus[tool.functionName] = tool.status;
    }
  }

  // Apply API overrides if available (API takes precedence)
  if (apiOverrides) {
    for (const [name, status] of Object.entries(apiOverrides.agents)) {
      agentStatus[name] = status;
    }
    for (const [name, status] of Object.entries(apiOverrides.tools)) {
      toolStatus[name] = status;
    }
  }

  /* -----------------------------------------------------------------------
   * Compute counts
   * ----------------------------------------------------------------------- */

  const agentEntries = Object.values(agentStatus);
  const toolEntries = Object.values(toolStatus);

  const agentShipped = agentEntries.filter((s) => s === 'shipped').length;
  const agentTotal = agentEntries.length;
  const toolShipped = toolEntries.filter((s) => s === 'shipped').length;
  const toolTotal = toolEntries.length;

  const loading = agentsLoading || toolsLoading || apiLoading;

  return {
    agentStatus,
    toolStatus,
    agentShipped,
    agentTotal,
    toolShipped,
    toolTotal,
    loading,
    refresh: fetchBuildState,
  };
}
