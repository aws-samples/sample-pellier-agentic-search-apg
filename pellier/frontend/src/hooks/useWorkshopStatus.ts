/**
 * useWorkshopStatus — polls /api/atelier/status to detect module completion.
 * Polls every 30 seconds. Tracks newly completed modules for celebration modal.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'

export interface ModuleStatus {
  complete: boolean
  label: string
  stubs: Record<string, boolean>
}

export interface WorkshopStatus {
  modules: {
    module1: ModuleStatus
    module2: ModuleStatus
    module3: ModuleStatus
  }
}

const POLL_INTERVAL_MS = 30_000
const MODULE_KEYS = ['module1', 'module2', 'module3'] as const
type ModuleKey = (typeof MODULE_KEYS)[number]

const MODE_MAP: Record<ModuleKey, string> = {
  module1: 'search',
  module2: 'agentic',
  module3: 'production',
}

export function useWorkshopStatus() {
  const [status, setStatus] = useState<WorkshopStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const prevStatus = useRef<WorkshopStatus | null>(null)
  const [newlyCompleted, setNewlyCompleted] = useState<string[]>([])

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/atelier/status')
      if (!res.ok) return
      const data: WorkshopStatus = await res.json()

      // Detect newly completed modules by comparing to previous
      if (prevStatus.current) {
        const newly: string[] = []
        for (const m of MODULE_KEYS) {
          if (!prevStatus.current.modules[m].complete && data.modules[m].complete) {
            newly.push(m)
          }
        }
        if (newly.length > 0) setNewlyCompleted(newly)
      }

      prevStatus.current = data
      setStatus(data)
    } catch {
      // Silently fail — workshop still works without status
    } finally {
      setLoading(false)
    }
  }, [])

  const dismissNewlyCompleted = useCallback(() => setNewlyCompleted([]), [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchStatus])

  // Derive completed workshop-step keys for Header pills
  const completedSteps = useMemo(() => {
    if (!status) return new Set<string>()
    const s = new Set<string>()
    for (const m of MODULE_KEYS) {
      if (status.modules[m].complete) s.add(MODE_MAP[m])
    }
    return s
  }, [status])

  return { status, loading, fetchStatus, newlyCompleted, dismissNewlyCompleted, completedSteps }
}
