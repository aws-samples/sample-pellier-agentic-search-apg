import { useEffect, useState } from 'react'

interface BuildStateResponse {
  tools?: Record<string, 'shipped' | 'exercise'>
}

/**
 * Whether the Builder's Session gap for Stock Keeper is still "open"
 * (floor_check treated as exercise by /api/atelier/build-state).
 *
 * Defaults to true when the endpoint is missing or errors — workshop
 * starter image — and flips false once the backend reports shipped.
 */
export function useFloorCheckWorkshopCue(): { showBuilderSessionGap: boolean } {
  const [showBuilderSessionGap, setShowBuilderSessionGap] = useState(true)

  useEffect(() => {
    let alive = true
    fetch('/api/atelier/build-state')
      .then((r) => (r.ok ? (r.json() as Promise<BuildStateResponse>) : null))
      .then((data) => {
        if (!alive || !data) return
        setShowBuilderSessionGap(data.tools?.floor_check !== 'shipped')
      })
      .catch(() => {
        if (alive) setShowBuilderSessionGap(true)
      })
    return () => {
      alive = false
    }
  }, [])

  return { showBuilderSessionGap }
}
