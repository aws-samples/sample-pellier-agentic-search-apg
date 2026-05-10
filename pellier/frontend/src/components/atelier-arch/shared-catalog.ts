/**
 * Shared catalog fetcher for the MCP and Tool Registry pages.
 *
 * Both pages pull from ``GET /api/atelier/catalog`` — the endpoint
 * returns agents, tools, and agent→tool grants in one payload. This
 * module exports the typed shapes and a tiny hook that memoizes the
 * fetch so we don't pay twice when both pages mount in the same
 * session.
 */
import { useEffect, useState } from 'react'

export interface AtelierAgent {
  name: string
  model: string
  role: string
}

export interface AtelierTool {
  name: string
  version: string
  headline: string
  description: string
  p50_ms: number
  gated?: boolean
}

export interface AtelierGrant {
  agent: string
  tool: string
  /** 'solid' = everyday, 'dashed' = read-only/rare, 'gated' = user-confirmation-required */
  style: 'solid' | 'dashed' | 'gated'
}

export interface AtelierCatalog {
  agents: AtelierAgent[]
  tools: AtelierTool[]
  grants: AtelierGrant[]
}

// Module-level cache — the catalog is static per boot, so fetching
// once per page session is fine.
let _cached: AtelierCatalog | null = null
let _pending: Promise<AtelierCatalog> | null = null

async function fetchCatalog(): Promise<AtelierCatalog> {
  if (_cached) return _cached
  if (_pending) return _pending
  _pending = fetch('/api/atelier/catalog')
    .then((r) => {
      if (!r.ok) throw new Error(`catalog fetch failed: ${r.status}`)
      return r.json() as Promise<AtelierCatalog>
    })
    .then((data) => {
      _cached = data
      return data
    })
    .finally(() => {
      _pending = null
    })
  return _pending
}

export function useCatalog() {
  const [catalog, setCatalog] = useState<AtelierCatalog | null>(_cached)
  const [loading, setLoading] = useState(!_cached)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (_cached) {
      setCatalog(_cached)
      setLoading(false)
      return
    }
    fetchCatalog()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err))
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { catalog, loading, error }
}

/**
 * Read the most recent chat turn's tool calls from localStorage.
 *
 * ``useAgentChat`` writes the latest tool_call events to localStorage
 * under ``pellier-last-tool-calls`` for the Atelier pages to consume
 * cross-route. Returns an empty list if nothing has fired yet.
 */
export interface RecentToolCall {
  /** Tool function name, e.g. ``find_pieces``. */
  tool: string
  /** Optional agent name that invoked the tool. */
  agent?: string
  /** Argument preview (truncated) for the live strip. */
  args?: string
  /** Elapsed ms for the call. */
  duration_ms?: number
  /** Timestamp (ms since epoch) when the call was made. */
  timestamp?: number
}

export function useRecentToolCalls(): RecentToolCall[] {
  const [calls, setCalls] = useState<RecentToolCall[]>(() => loadToolCalls())
  useEffect(() => {
    const tick = () => {
      const next = loadToolCalls()
      setCalls((prev) => {
        // Shallow compare by length + last timestamp
        if (prev.length === next.length) {
          const lastP = prev[prev.length - 1]
          const lastN = next[next.length - 1]
          if (!lastP && !lastN) return prev
          if (lastP?.timestamp === lastN?.timestamp && lastP?.tool === lastN?.tool) {
            return prev
          }
        }
        return next
      })
    }
    const t = setInterval(tick, 1500)
    return () => clearInterval(t)
  }, [])
  return calls
}

function loadToolCalls(): RecentToolCall[] {
  try {
    const raw = localStorage.getItem('pellier-last-tool-calls')
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}


/* ==========================================================================
 * Runtime timing — per-layer wall-clock for the most recent turn.
 *
 * Written by ``useAgentChat`` on each ``runtime_timing`` SSE event.
 * Until the backend ships that event, the hook returns ``null`` and
 * the Runtime page renders with demo-data caption.
 * ========================================================================== */

export interface RuntimeTiming {
  /** Timing per layer, in ms. */
  layers: {
    fastpath: number
    intent: number
    skill_router: number
    orchestrator: number
    specialist: number
    tools: number
    stream: number
  }
  /** Wall-clock to first streamed token, in ms. */
  ttft_ms: number
  /** Wall-clock total duration, in ms. */
  total_ms: number
  /** Epoch ms the turn completed. */
  timestamp: number
}

const RUNTIME_TIMING_KEY = 'pellier-last-runtime-timing'

export function useRuntimeTiming(): RuntimeTiming | null {
  const [timing, setTiming] = useState<RuntimeTiming | null>(loadRuntimeTiming)
  useEffect(() => {
    const tick = () => {
      const next = loadRuntimeTiming()
      setTiming((prev) => {
        if (prev?.timestamp === next?.timestamp) return prev
        return next
      })
    }
    const t = setInterval(tick, 1500)
    return () => clearInterval(t)
  }, [])
  return timing
}

function loadRuntimeTiming(): RuntimeTiming | null {
  try {
    const raw = localStorage.getItem(RUNTIME_TIMING_KEY)
    if (!raw) return null
    return JSON.parse(raw) as RuntimeTiming
  } catch {
    return null
  }
}

/* ==========================================================================
 * DB queries — per-turn database operations (read / write) with SQL.
 *
 * Written by ``useAgentChat`` on each ``db_queries`` SSE event.
 * Until the backend ships that event, the hook returns an empty list
 * and State Management renders with demo-data caption.
 * ========================================================================== */

export interface DbQuery {
  op: 'READ' | 'WRITE'
  table: string
  sql: string
  duration_ms: number
  timestamp: number
}

const DB_QUERIES_KEY = 'pellier-last-db-queries'

export function useDbQueries(): DbQuery[] {
  const [queries, setQueries] = useState<DbQuery[]>(loadDbQueries)
  useEffect(() => {
    const tick = () => {
      const next = loadDbQueries()
      setQueries((prev) => {
        if (prev.length === next.length) {
          const lastP = prev[prev.length - 1]
          const lastN = next[next.length - 1]
          if (lastP?.timestamp === lastN?.timestamp && lastP?.sql === lastN?.sql) {
            return prev
          }
        }
        return next
      })
    }
    const t = setInterval(tick, 1500)
    return () => clearInterval(t)
  }, [])
  return queries
}

function loadDbQueries(): DbQuery[] {
  try {
    const raw = localStorage.getItem(DB_QUERIES_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
