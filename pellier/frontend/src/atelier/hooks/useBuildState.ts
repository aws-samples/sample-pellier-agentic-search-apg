/**
 * useBuildState — Determines shipped vs exercise status for tools and agents.
 *
 * Provides an abstraction layer that can be backed by:
 *   1. Fixture data (default — reads status from agents.json / tools.json)
 *   2. A backend endpoint (GET /api/atelier/build-state) when available
 *   3. File-existence checks via a future backend probe
 *
 * Consumers (Agents, Tools surfaces, WorkshopProgressStrip) use this hook
 * to get the canonical status of each item. When an item transitions from
 * exercise → shipped, the UI updates automatically (dashed → solid styling).
 *
 * Requirements: 17.1, 17.2, 17.3
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAtelierData } from './useAtelierData';
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
  /** Error message if build state detection failed */
  error: string | null;
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
  const { data: agents, loading: agentsLoading } = useAtelierData<Agent[]>({
    key: 'agents',
  });
  const { data: tools, loading: toolsLoading } = useAtelierData<Tool[]>({
    key: 'tools',
  });

  const [apiOverrides, setApiOverrides] = useState<BuildStateApiResponse | null>(null);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  /**
   * Attempt to fetch build state from the backend.
   * Falls back silently to fixture data if the endpoint is unavailable.
   */
  const fetchBuildState = useCallback(async () => {
    const currentId = ++requestIdRef.current;
    setApiLoading(true);
    setApiError(null);

    try {
      const res = await fetch('/api/atelier/build-state');
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
  const error = apiError;

  return {
    agentStatus,
    toolStatus,
    agentShipped,
    agentTotal,
    toolShipped,
    toolTotal,
    loading,
    error,
    refresh: fetchBuildState,
  };
}
