/**
 * useScrollAndFlash — cross-panel scroll + 800ms terracotta pulse for
 * the Atelier's citation / "view trace" interactions.
 *
 * Given a scroll-container ref, returns a ``scrollToPanel(ref)``
 * function that:
 *   1. Resolves the reference to a DOM node within the container.
 *   2. Scrolls the container to bring the node into view.
 *   3. Applies a ``data-flash="true"`` attribute that CSS animates
 *      (800ms terracotta border pulse) via the ``.panel-flash`` class
 *      defined in index.css.
 *
 * Reference resolution is forgiving:
 *   - ``"plan"``           → the PlanCard (``data-testid="plan-card"``)
 *   - panel tag string     → ``[data-testid="panel-card-<tag>"]``
 *   - ``"trace N"``         → the Nth panel card (1-based; via panel
 *                           ``trace_index`` attribute if present, else
 *                           by DOM index)
 *
 * If the reference can't be resolved, the call is a no-op — the
 * citation pill still renders and the click doesn't crash.
 */
import { useCallback, useRef, type MutableRefObject } from 'react'

const FLASH_MS = 800

export interface UseScrollAndFlash {
  /** Attach to the scroll-container that holds the PanelCards. */
  containerRef: MutableRefObject<HTMLDivElement | null>
  /** Call with a trace reference — "plan", a panel tag, or "trace N". */
  scrollToTrace: (ref: string) => void
}

export function useScrollAndFlash(): UseScrollAndFlash {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const pendingTimeouts = useRef<number[]>([])

  const scrollToTrace = useCallback((traceRef: string) => {
    const container = containerRef.current
    if (!container) return
    const target = resolveTarget(container, traceRef)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.setAttribute('data-flash', 'true')
    const timer = window.setTimeout(() => {
      target.removeAttribute('data-flash')
    }, FLASH_MS)
    pendingTimeouts.current.push(timer)
  }, [])

  return { containerRef, scrollToTrace }
}

function resolveTarget(
  container: HTMLElement,
  traceRef: string,
): HTMLElement | null {
  if (traceRef === 'plan') {
    return container.querySelector<HTMLElement>('[data-testid="plan-card"]')
  }
  // "trace 7" → 7th panel card (1-based by panel emission order).
  const traceMatch = traceRef.match(/^trace\s*(\d+)$/i)
  if (traceMatch) {
    const idx = parseInt(traceMatch[1], 10)
    const panels = container.querySelectorAll<HTMLElement>(
      '[data-testid^="panel-card-"]',
    )
    return panels[idx - 1] ?? null
  }
  // Fall back to the panel tag lookup.
  return container.querySelector<HTMLElement>(
    `[data-testid="panel-card-${cssEscape(traceRef)}"]`,
  )
}

/**
 * CSS.escape isn't available in all jsdom versions; fall back to a
 * minimal escaper that handles the characters that appear in our
 * panel tags ("·" and spaces).
 */
function cssEscape(value: string): string {
  if (typeof (globalThis as unknown as { CSS?: { escape?: (s: string) => string } }).CSS?.escape === 'function') {
    return (globalThis as unknown as { CSS: { escape: (s: string) => string } }).CSS.escape(value)
  }
  return value.replace(/"/g, '\\"')
}
