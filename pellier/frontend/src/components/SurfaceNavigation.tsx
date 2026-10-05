import { useLayoutEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useUI } from '../contexts/UIContext'
import ThemeControl from '../theme/ThemeControl'
import { BuilderViewToggle } from './turn'
import Wordmark from './Wordmark'
import '../styles/surface-navigation.css'
import '../styles/turn.css'

type Surface = 'storefront' | 'operator'

const SURFACES = [
  { id: 'storefront', label: 'Storefront', purpose: 'Shopper conversations and the collection' },
  { id: 'operator', label: 'Operator', purpose: 'Staff investigations and human review' },
] as const

function surfaceFor(path: string): Surface {
  if (path === '/operator' || path.startsWith('/operator/')) return 'operator'
  return 'storefront'
}

/**
 * The shared header: the wordmark, the Storefront and Operator switch, the
 * theme control and the Ask Pellier button. Remember locations, not evidence:
 * each destination still reads its records through its existing API boundary.
 * Keeping the query string preserves an exact review, customer, lab, or turn
 * when someone returns from the other surface.
 *
 * The Ask Pellier button opens the docked panel on storefront routes; its
 * copper dot pulses only while a turn runs (signature element 2).
 *
 * The Builder view switch is global: it governs the storefront's "How it
 * ranked" panel, the dock's evidence and the Operator's investigation. On a
 * phone it shares the second row with the surface switch.
 */
export default function SurfaceNavigation() {
  const { pathname, search, hash } = useLocation()
  const { openModal, turnRunning } = useUI()
  const active = surfaceFor(pathname)
  const [destinations, setDestinations] = useState<Record<Surface, string>>({
    storefront: '/',
    operator: '/operator/reviews',
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
      <nav aria-label="Pellier home">
        <Wordmark />
      </nav>
      <nav aria-label="Pellier surfaces" className="pellier-surface-links">
        {SURFACES.map(surface => (
          <Link
            key={surface.id}
            to={destinations[surface.id]}
            className="pellier-surface-link"
            aria-current={active === surface.id ? 'page' : undefined}
            data-surface={surface.id}
            title={`${surface.purpose}. Return to your last ${surface.label} view.`}
          >
            <span>{surface.label}</span>
          </Link>
        ))}
      </nav>
      {pathname !== '/signin' ? <BuilderViewToggle className="pellier-builder-toggle" /> : null}
      <div className="pellier-surface-tools">
        <ThemeControl />
        {active === 'storefront' && pathname !== '/signin' ? (
          <button
            type="button"
            className="pellier-ask-button"
            data-testid="header-ask-pellier"
            data-running={turnRunning ? 'true' : 'false'}
            onClick={() => openModal('drawer')}
          >
            <span className="tn-dot" aria-hidden="true" />
            Ask Pellier
          </button>
        ) : null}
      </div>
    </div>
  )
}
