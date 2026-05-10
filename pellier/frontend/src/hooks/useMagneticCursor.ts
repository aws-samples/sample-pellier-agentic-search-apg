/**
 * Magnetic Cursor Hook — Adds a subtle pull effect on CTA buttons.
 * On mouse move, translates the element slightly toward the cursor.
 */
import { useRef, useCallback } from 'react'

export function useMagneticCursor(strength = 0.2) {
  const ref = useRef<HTMLElement>(null)

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const dx = (e.clientX - cx) * strength
    const dy = (e.clientY - cy) * strength
    el.style.transform = `translate(${dx}px, ${dy}px)`
  }, [strength])

  const handleMouseLeave = useCallback(() => {
    const el = ref.current
    if (!el) return
    el.style.transform = ''
    el.style.transition = 'transform 0.3s ease-out'
    setTimeout(() => {
      if (el) el.style.transition = ''
    }, 300)
  }, [])

  return { ref, onMouseMove: handleMouseMove, onMouseLeave: handleMouseLeave }
}
