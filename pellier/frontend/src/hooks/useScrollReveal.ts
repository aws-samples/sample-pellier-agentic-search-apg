/**
 * useScrollReveal — parallax reveal hook for the storefront product grid.
 *
 * Validates Requirements 1.6.2, 1.6.3, and 1.6.4.
 *
 * Behavior (per `storefront.md` `parallax-card` spec):
 *   - Observes the element with IntersectionObserver.
 *   - Defaults: `threshold: 0.05`, `rootMargin: '0px 0px -5% 0px'`.
 *   - When the element enters the viewport, `revealed` flips to `true`
 *     after an `index * staggerMs` delay (default `staggerMs: 220`).
 *     The grid passes its card's row-wise index so each subsequent card
 *     starts 220ms after its left neighbor.
 *   - `revealed` only flips once per mount — subsequent scroll-backs do
 *     NOT re-trigger the animation (Req 1.6.4). Re-observation on
 *     preference save is handled externally by remounting the grid with
 *     `key={prefsVersion}` (Req 1.6.6).
 *
 * The hook intentionally returns just a `ref` + `revealed` boolean. The
 * consumer (typically `<ProductCard>`) owns the CSS transition:
 *
 *   transition:
 *     opacity 1100ms cubic-bezier(0.16, 1, 0.3, 1),
 *     transform 1200ms cubic-bezier(0.16, 1, 0.3, 1);
 *   transform: translateY(56px) scale(0.975);   // pre-reveal
 *   transform: translateY(0)    scale(1);       // revealed
 *
 * Back-compat: the pre-task-4.6 signature `useScrollReveal(0.15)` accepted
 * a `threshold` number and returned `{ ref, scale, opacity, y }`. That
 * legacy hook was unused by any rendered component (replaced by
 * framer-motion `whileInView`) — `App.tsx` has a comment noting as much.
 * The new signature takes an options object and returns `{ ref, revealed }`.
 * If future code needs the legacy shape, derive `scale/opacity/y` from
 * `revealed` in the consumer.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export interface UseScrollRevealOptions {
  /** IntersectionObserver threshold. Defaults to 0.05 per storefront.md. */
  threshold?: number
  /**
   * IntersectionObserver `rootMargin`. Defaults to `'0px 0px -5% 0px'`
   * per storefront.md so cards trigger slightly before the hard bottom edge.
   */
  rootMargin?: string
  /**
   * Per-card stagger delay in milliseconds. Each card reveals after
   * `index * staggerMs`. Defaults to 220ms per storefront.md.
   */
  staggerMs?: number
  /**
   * Row-wise index of this card within the grid. Used to compute the
   * stagger delay. Defaults to 0 (no delay) for solo reveals.
   */
  index?: number
}

export interface UseScrollRevealResult<T extends HTMLElement> {
  /** Callback ref — attach to the element you want revealed. */
  ref: (node: T | null) => void
  /** Flips to `true` once the element has entered the viewport. */
  revealed: boolean
}

export function useScrollReveal<T extends HTMLElement = HTMLElement>(
  options: UseScrollRevealOptions = {},
): UseScrollRevealResult<T> {
  const {
    threshold = 0.05,
    rootMargin = '0px 0px -5% 0px',
    staggerMs = 220,
    index = 0,
  } = options

  const [revealed, setRevealed] = useState(false)
  // Track the element + the active observer so we can clean up on unmount
  // and on ref swap without leaking listeners.
  const elRef = useRef<T | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Once revealed we must never re-trigger for the lifetime of this mount
  // (Req 1.6.4). Remounting via `key={prefsVersion}` is the single exception
  // (Req 1.6.6) — handled by the parent grid, not here.
  const revealedRef = useRef(false)

  const detach = useCallback(() => {
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  const ref = useCallback(
    (node: T | null) => {
      // Ref swap: tear down the old observer first.
      detach()
      elRef.current = node
      if (!node) return

      // Environments without IntersectionObserver (old jsdom, SSR) reveal
      // immediately so content isn't stuck invisible. This keeps tests
      // deterministic when they don't install a polyfill.
      if (
        typeof window === 'undefined' ||
        typeof window.IntersectionObserver === 'undefined'
      ) {
        if (!revealedRef.current) {
          revealedRef.current = true
          setRevealed(true)
        }
        return
      }

      const observer = new IntersectionObserver(
        entries => {
          for (const entry of entries) {
            if (entry.isIntersecting && !revealedRef.current) {
              // Stagger by row-wise index. Using a single setTimeout keeps
              // the reveal cancellable if the component unmounts mid-delay.
              const delay = Math.max(0, index) * staggerMs
              timeoutRef.current = setTimeout(() => {
                revealedRef.current = true
                setRevealed(true)
                // Stop observing after the first intersection — parallax
                // is once per card per page view (Req 1.6.4).
                observer.disconnect()
                observerRef.current = null
              }, delay)
            }
          }
        },
        { threshold, rootMargin },
      )
      observer.observe(node)
      observerRef.current = observer
    },
    [detach, index, rootMargin, staggerMs, threshold],
  )

  useEffect(() => {
    return detach
  }, [detach])

  return { ref, revealed }
}
