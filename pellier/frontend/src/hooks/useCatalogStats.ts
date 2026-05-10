/**
 * useCatalogStats — live catalog size for the storefront welcome card.
 *
 * Fetches GET /api/storefront/catalog-stats on mount and refreshes on a
 * gentle interval while the tab is visible. The storefront greeting
 * cites real numbers (product count, category count, today's
 * standout) so we never ship a hardcoded "444" that drifts as the
 * catalog grows or shrinks.
 *
 * Returns ``null`` until the first response lands so callers can show
 * a graceful fallback ("the boutique") during the first paint. On
 * fetch failure, stays on the last successful payload — the endpoint
 * is contract-bound to never 5xx but network blips happen.
 */
import { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''
const REFRESH_MS = 60_000 // catalog size moves on the order of minutes

export interface CatalogStats {
  product_count: number
  category_count: number
  standout_name: string | null
  standout_category: string | null
  generated_at: string
}

export function useCatalogStats(): CatalogStats | null {
  const [stats, setStats] = useState<CatalogStats | null>(null)

  const fetchStats = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/storefront/catalog-stats`, {
        signal,
      })
      if (!res.ok) return
      const body = (await res.json()) as CatalogStats
      setStats(body)
    } catch (e) {
      // AbortError on unmount / visibility change is expected — swallow.
      if ((e as { name?: string })?.name !== 'AbortError') {
        console.warn('catalog-stats fetch failed:', e)
      }
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetchStats(controller.signal)

    let interval: ReturnType<typeof setInterval> | null = null
    const start = () => {
      if (interval) return
      interval = setInterval(() => fetchStats(), REFRESH_MS)
    }
    const stop = () => {
      if (interval) clearInterval(interval)
      interval = null
    }

    if (document.visibilityState === 'visible') start()
    const onVis = () => {
      if (document.visibilityState === 'visible') {
        fetchStats()
        start()
      } else {
        stop()
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      controller.abort()
      stop()
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [fetchStats])

  return stats
}
