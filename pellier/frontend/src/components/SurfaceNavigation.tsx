import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { NAV } from '../copy'
import { useUI } from '../contexts/UIContext'
import ThemeControl from '../theme/ThemeControl'
import { TourHost, TourReplayButton } from './SpotlightTour'
import { BuilderViewToggle } from './turn'
import Wordmark from './Wordmark'
import '../styles/surface-navigation.css'
import '../styles/turn.css'

/** The width at or below which the switches fold into the menu. Keep in step with surface-navigation.css. */
const PHONE_MEDIA = '(max-width: 560px)'

function useIsPhone(): boolean {
  const [phone, setPhone] = useState(() => window.matchMedia?.(PHONE_MEDIA).matches ?? false)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia(PHONE_MEDIA)
    const sync = () => setPhone(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])
  return phone
}

type Surface = 'storefront' | 'operator'

const SURFACES = [
  { id: 'storefront', label: 'Storefront', purpose: 'Shopper conversations and the collection' },
  { id: 'operator', label: 'Operator', purpose: 'Staff investigations and human review' },
] as const

/** On a phone the storefront's own links join this menu, so the page has one menu button. */
const STOREFRONT_LINKS = [
  { label: NAV.SHOP, to: '/#shop', current: (path: string) => path === '/' || path.startsWith('/product/') },
  { label: NAV.STORIES, to: '/storyboard', current: (path: string) => path === '/storyboard' },
  { label: NAV.ABOUT, to: '/about', current: (path: string) => path === '/about' },
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
 * phone (560px and narrower) the surface switch, the Builder view switch and
 * the theme control fold into one menu beside Ask Pellier, so the bar stays
 * one row and every target is at least 44px. On the Storefront the menu also
 * holds Shop, Stories and About, and the storefront row drops its own menu
 * button, so a phone shows one menu.
 *
 * The whole bar is a labelled region, so the switches sit inside a landmark.
 * On the Storefront it also holds the short tour (SpotlightTour): its replay
 * button beside the theme control, and the host that opens it, outside the
 * menu so a first visit on a phone still opens it.
 */
export default function SurfaceNavigation() {
  const { pathname, search, hash } = useLocation()
  const { openModal, turnRunning } = useUI()
  const active = surfaceFor(pathname)
  const onStorefront = active === 'storefront' && pathname !== '/signin'
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

  const phone = useIsPhone()
  const [menuOpen, setMenuOpen] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const folded = phone && !menuOpen

  useEffect(() => {
    if (!phone) setMenuOpen(false)
  }, [phone])

  useEffect(() => setMenuOpen(false), [pathname])

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setMenuOpen(false)
      menuButtonRef.current?.focus()
    }
    const onOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !barRef.current?.contains(event.target)) setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onOutside)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onOutside)
    }
  }, [menuOpen])

  return (
    <div
      ref={barRef}
      className="pellier-surface-bar"
      role="region"
      aria-label="Pellier controls"
      data-testid="surface-navigation"
    >
      <nav aria-label="Pellier home">
        <Wordmark />
      </nav>
      {folded ? null : (
        <div
          className="pellier-surface-menu"
          id="pellier-surface-menu"
          data-testid="surface-menu"
          data-phone={phone ? 'true' : 'false'}
        >
          {phone && onStorefront ? (
            <nav aria-label="Storefront" className="pellier-surface-storefront">
              {STOREFRONT_LINKS.map(link => (
                <Link
                  key={link.to}
                  to={link.to}
                  className="pellier-nav-link"
                  aria-current={link.current(pathname) ? 'page' : undefined}
                  onClick={() => setMenuOpen(false)}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          ) : null}
          <nav aria-label="Pellier surfaces" className="pellier-surface-links">
            {SURFACES.map(surface => (
              <Link
                key={surface.id}
                to={destinations[surface.id]}
                className="pellier-surface-link"
                aria-current={active === surface.id ? 'page' : undefined}
                data-surface={surface.id}
                data-tour={surface.id === 'operator' ? 'operator' : undefined}
                title={`${surface.purpose}. Return to your last ${surface.label} view.`}
              >
                <span>{surface.label}</span>
              </Link>
            ))}
          </nav>
          {pathname !== '/signin' ? <BuilderViewToggle className="pellier-builder-toggle" /> : null}
          {onStorefront ? <TourReplayButton /> : null}
          <ThemeControl />
        </div>
      )}
      {onStorefront || phone ? (
      <div className="pellier-surface-tools">
        {onStorefront ? (
          <button
            type="button"
            className="pellier-ask-button"
            data-testid="header-ask-pellier"
            data-tour="ask-pellier"
            data-running={turnRunning ? 'true' : 'false'}
            onClick={() => openModal('drawer')}
          >
            <span className="tn-dot" aria-hidden="true" />
            Ask Pellier
          </button>
        ) : null}
        {phone ? (
          <button
            ref={menuButtonRef}
            type="button"
            className="pellier-surface-menu-button"
            data-testid="surface-menu-button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="pellier-surface-menu"
            onClick={() => setMenuOpen(open => !open)}
          >
            {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
        ) : null}
      </div>
      ) : null}
      {onStorefront ? <TourHost /> : null}
    </div>
  )
}
