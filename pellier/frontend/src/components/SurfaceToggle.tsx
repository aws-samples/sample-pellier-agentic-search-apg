/**
 * SurfaceToggle — segmented control that pairs the shopper-facing
 * storefront (`/`) with the operator-facing Atelier surface.
 *
 * Replaces the standalone "Workshop" text link that used to sit in
 * the Header. The pair is a single source of truth for "which surface
 * am I on" — the active half highlights based on the current
 * ``useLocation().pathname`` so the control works whether the user
 * got here via the toggle, a direct URL, or a back/forward nav.
 *
 * Keyboard: arrow-left / arrow-right swap focus + navigate; enter and
 * space on a button navigate.
 *
 * Responsive: visible ≥ 640px (sm). Below that the segmented control
 * compresses visually too far; we fall back to the same control at a
 * smaller size rather than hide it, because surface-switching is the
 * single most important navigation decision on either page.
 */
import { Link, useLocation } from 'react-router-dom'
import { useRef } from 'react'
import { SURFACE_TOGGLE } from '../copy'
import { cssVar as c } from '../design/cssVars'


type Surface = 'storefront' | 'atelier'

const SEGMENTS: Array<{ key: Surface; label: string; path: string }> = [
  { key: 'storefront', label: SURFACE_TOGGLE.STOREFRONT, path: '/' },
  { key: 'atelier', label: SURFACE_TOGGLE.ATELIER, path: '/atelier' },
]

function currentSurface(pathname: string): Surface {
  return pathname.startsWith('/atelier') ? 'atelier' : 'storefront'
}

export default function SurfaceToggle() {
  const { pathname } = useLocation()
  const active = currentSurface(pathname)
  const refs = useRef<Array<HTMLAnchorElement | null>>([])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLAnchorElement>, index: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const next =
      e.key === 'ArrowRight'
        ? Math.min(SEGMENTS.length - 1, index + 1)
        : Math.max(0, index - 1)
    refs.current[next]?.focus()
  }

  return (
    <div
      data-testid="surface-toggle"
      role="group"
      aria-label={SURFACE_TOGGLE.ARIA_LABEL}
      className="inline-flex items-center rounded-full p-[3px]"
      style={{
        background: 'rgba(45, 24, 16, 0.06)',
        border: '1px solid color-mix(in srgb, var(--ink-quiet) 21%, transparent)',
      }}
    >
      {SEGMENTS.map((seg, i) => {
        const isActive = seg.key === active
        return (
          <Link
            key={seg.key}
            to={seg.path}
            data-testid={`surface-toggle-${seg.key}`}
            data-active={isActive ? 'true' : 'false'}
            aria-current={isActive ? 'page' : undefined}
            ref={(el) => {
              refs.current[i] = el
            }}
            onKeyDown={(e) => handleKeyDown(e, i)}
            className="px-3.5 sm:px-4 py-1 rounded-full text-[12.5px] font-medium transition-colors"
            style={{
              background: isActive ? c.ink : 'transparent',
              color: isActive ? c.bg : c.ink2,
            }}
          >
            {seg.label}
          </Link>
        )
      })}
    </div>
  )
}
