import { useLayoutEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import '../styles/surface-navigation.css'

type Surface = 'storefront' | 'operator' | 'observatory'

const SURFACES = [
  { id: 'storefront', number: '1', label: 'Storefront' },
  { id: 'operator', number: '2', label: 'Operator' },
  { id: 'observatory', number: '3', label: 'Observatory' },
] as const

function surfaceFor(path: string): Surface {
  if (path === '/operator' || path.startsWith('/operator/')) return 'operator'
  if (path === '/observatory' || path.startsWith('/observatory/')) return 'observatory'
  return 'storefront'
}

/**
 * One navigation across the three work areas. Remember locations, not evidence:
 * each destination still reads its records through its existing API boundary.
 * Keeping the query string preserves an exact review, customer, lab, or turn
 * when someone returns from another surface.
 */
export default function SurfaceNavigation() {
  const { pathname, search, hash } = useLocation()
  const active = surfaceFor(pathname)
  const [destinations, setDestinations] = useState<Record<Surface, string>>({
    storefront: '/',
    operator: '/operator/reviews',
    observatory: '/observatory',
  })

  useLayoutEffect(() => {
    // Sign-in is a transient route, not the shopper's place in the collection.
    if (pathname === '/signin') return
    const destination = `${pathname}${search}${hash}`
    setDestinations(current =>
      current[active] === destination ? current : { ...current, [active]: destination },
    )
  }, [active, pathname, search, hash])

  return (
    <div className="pellier-surface-bar" data-testid="surface-navigation">
      <Link to="/" className="pellier-brand" aria-label="Pellier home">
        <span className="pellier-brand-full" aria-hidden="true">pellier</span>
        <span className="pellier-brand-small" aria-hidden="true">p</span>
        <span className="pellier-brand-dot" aria-hidden="true">.</span>
      </Link>
      <nav aria-label="Pellier surfaces" className="pellier-surface-links">
        {SURFACES.map(surface => (
          <Link
            key={surface.id}
            to={destinations[surface.id]}
            className="pellier-surface-link"
            aria-current={active === surface.id ? 'page' : undefined}
            data-surface={surface.id}
            title={surface.id === 'observatory'
              ? 'Labs and evidence. Return to your last Observatory view.'
              : `Return to your ${surface.label.toLowerCase()} view`}
          >
            <span className="pellier-surface-number" aria-hidden="true">{surface.number}</span>
            <span>{surface.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  )
}
