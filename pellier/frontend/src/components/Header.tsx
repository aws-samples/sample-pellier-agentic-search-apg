/**
 * Header — Pellier sticky header.
 *
 * Storefront navigation beneath the shared SurfaceNavigation. Collection,
 * Stories, Ask Pellier, and About remain local; the global bar owns the
 * wordmark and the three surface destinations. Persona and bag controls
 * preserve their existing interaction and identity boundaries.
 *
 * Visitors without a scenario see a "Select scenario" pill. Once a persona is
 * active, the same header pill opens the shared portrait-led PersonaModal
 * used by Pellier Observatory. Neither state is a Cognito sign-in.
 *
 * Validates Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3.
 *
 * Copy comes from `copy.ts`. Design tokens from `design/tokens.ts` and
 * Tailwind extended config.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { NAV, SCENARIO } from '../copy'
import { Avatar } from '../design/primitives'
import { getPersonaPhoto } from '../data/personaPhotos'
import { IconButton } from '../design/primitives'
import PersonaModal from './PersonaModal'
import {
  Search,
  ShoppingBag,
  User as UserIcon,
  ChevronDown,
  Menu,
  X,
} from 'lucide-react'

// Keep old NavItem values for backward compatibility with consuming pages,
// plus new values for the redesigned nav.
export type NavItem =
  | 'home'
  | 'shop'
  | 'storyboard'
  | 'stories'
  | 'discover'
  | 'about'
  | 'account'
  | 'ask-pellier'

interface HeaderProps {
  /** Which nav item is the current page — gets the espresso highlight. Defaults to 'home'. */
  current?: NavItem
  /** Optional click handler fired when any nav link is activated. */
  onNavigate?: (item: NavItem) => void
}

/** The four nav items rendered in the redesigned header. */
const NAV_ITEMS: Array<{ item: NavItem; label: string }> = [
  { item: 'shop', label: NAV.SHOP },
  { item: 'stories', label: NAV.STORIES },
  { item: 'ask-pellier', label: NAV.ASK_PELLIER },
  { item: 'about', label: NAV.ABOUT },
]

const MENU_EASE: [number, number, number, number] = [0.16, 1, 0.3, 1]

// ---------------------------------------------------------------------------
// NavLink
// ---------------------------------------------------------------------------

interface NavLinkProps {
  item: NavItem
  label: string
  current: NavItem
  onClick?: (item: NavItem) => void
}

function NavLink({ item, label, current, onClick }: NavLinkProps) {
  const isCurrent = current === item || (current === 'home' && item === 'shop')
  const shared = {
    'data-nav-item': item,
    'data-current': isCurrent ? 'true' : 'false',
    'aria-current': isCurrent ? 'page' as const : undefined,
    className: 'pellier-nav-link',
  }
  if (item === 'ask-pellier') {
    return <button {...shared} type="button" onClick={() => onClick?.(item)}>{label}</button>
  }
  const to = item === 'stories' ? '/storyboard' : item === 'about' ? '/about' : '/#shop'
  return (
    <Link {...shared} to={to} onClick={(event) => {
      // Preserve open-in-new-tab and the browser's link menu.
      if (onClick && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
        event.preventDefault()
        onClick(item)
      }
    }}>{label}</Link>
  )
}

// ---------------------------------------------------------------------------
// Signed-out persona menu
// ---------------------------------------------------------------------------

function SignedOutPersonaTrigger({
  open,
  onOpen,
}: {
  open: boolean
  onOpen: () => void
}) {
  // The signed-out pill used to open a compact dropdown of the three
  // personas, a second chooser beside the modal the active-persona pill
  // already opens. Both now open the same three-card modal, which the
  // header owns so the signed-out Ask Pellier item can open it too.
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="persona-pill"
      className={[
        'pellier-account-pill',
        'flex min-h-[44px] items-center gap-2 text-[13.5px] transition-colors duration-fade ease-out',
        'cursor-pointer rounded-full',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-espresso focus-visible:ring-offset-2',
      ].join(' ')}
      style={{ padding: '7px 14px' }}
      aria-label={SCENARIO.SELECT}
      aria-haspopup="dialog"
      aria-expanded={open}
    >
      <UserIcon className="w-4 h-4" aria-hidden />
      <span className="hidden whitespace-nowrap sm:inline" style={{ fontFamily: 'var(--sans)' }}>{SCENARIO.SELECT}</span>
      <span className="hidden whitespace-nowrap min-[360px]:inline sm:hidden">Scenario</span>
    </button>
  )
}

function AuthenticatedPersonaTrigger() {
  const { persona } = usePersona()
  const [open, setOpen] = useState(false)

  if (!persona) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="persona-pill"
        className={[
          'pellier-account-pill',
          'flex min-h-[44px] items-center gap-2 text-[13.5px] transition-colors duration-fade ease-out',
          'cursor-pointer rounded-full',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-espresso focus-visible:ring-offset-2',
        ].join(' ')}
        style={{
          padding: '4px 12px 4px 4px',
          background: 'var(--ink)',
          color: 'var(--cream)',
          border: '1px solid var(--ink)',
        }}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Avatar
          initial={persona.avatar_initial}
          bgColor={persona.avatar_color}
          photoUrl={getPersonaPhoto(persona.id)}
          size="sm"
        />
        <span
          className="text-cream-50 truncate"
          style={{
            fontFamily: 'var(--sans)',
            fontSize: 13,
            fontWeight: 500,
            maxWidth: 118,
          }}
        >
          {persona.display_name}
        </span>
        <ChevronDown
          size={14}
          className="text-cream-50 opacity-60"
          aria-hidden
        />
      </button>
      <PersonaModal open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function PersonaAccountControl({
  chooserOpen,
  onOpenChooser,
}: {
  chooserOpen: boolean
  onOpenChooser: () => void
}) {
  const { persona } = usePersona()
  return persona ? (
    <AuthenticatedPersonaTrigger />
  ) : (
    <SignedOutPersonaTrigger open={chooserOpen} onOpen={onOpenChooser} />
  )
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

export default function Header({
  current = 'home',
  onNavigate,
}: HeaderProps) {
  const { items: cartItems, setCartOpen } = useCart()
  const { openModal } = useUI()
  const { persona } = usePersona()
  const headerRef = useRef<HTMLElement>(null)
  const menuToggleRef = useRef<HTMLButtonElement>(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [chooserOpen, setChooserOpen] = useState(false)
  const reduceMotion = Boolean(useReducedMotion())
  const cartItemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0)
  const navItems = NAV_ITEMS
  const openChooser = useCallback(() => setChooserOpen(true), [])

  // The storefront's search is Pellier - the chat drawer. Clicking the
  // Search icon opens the same concierge the pill uses, which keeps the
  // header honest: one search surface, two entry points. Signed out, both
  // lead to the chooser first, because the concierge needs a shopper.
  const handleSearchClick = useCallback(() => {
    if (!persona) {
      setChooserOpen(true)
      return
    }
    openModal('drawer')
  }, [persona, openModal])

  const handleNavigate = useCallback(
    (item: NavItem) => {
      setMobileMenuOpen(false)
      if (item === 'ask-pellier' && !persona) {
        setChooserOpen(true)
        return
      }
      onNavigate?.(item)
    },
    [onNavigate, persona],
  )

  useEffect(() => {
    if (!mobileMenuOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false)
        menuToggleRef.current?.focus()
      }
    }
    const handleOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !headerRef.current?.contains(event.target)) setMobileMenuOpen(false)
    }
    const handleFocusOut = (event: FocusEvent) => {
      if (event.target instanceof Node && !headerRef.current?.contains(event.target)) setMobileMenuOpen(false)
    }
    const desktop = window.matchMedia('(min-width: 1024px)')
    const closeOnDesktop = () => { if (desktop.matches) setMobileMenuOpen(false) }
    window.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handleOutside)
    document.addEventListener('focusin', handleFocusOut)
    desktop.addEventListener('change', closeOnDesktop)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handleOutside)
      document.removeEventListener('focusin', handleFocusOut)
      desktop.removeEventListener('change', closeOnDesktop)
    }
  }, [mobileMenuOpen])


  return (
    <header
      ref={headerRef}
      role="banner"
      data-testid="sticky-header"
      className="pellier-storefront-header sticky z-40 w-full border-b border-sand/50"
      style={{
        background: 'var(--header-bg)',
        WebkitBackdropFilter: 'blur(12px)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <nav
        aria-label="Primary"
        className="relative h-[var(--pellier-storefront-nav-height,60px)]"
        style={{ padding: '0 clamp(16px, 4vw, 48px)' }}
      >
        <div className="mx-auto flex h-full items-center justify-between gap-4">
          {/* Left: four text nav items */}
          <div className="hidden min-w-0 items-center gap-5 lg:flex">
            {navItems.map(({ item, label }) => (
              <NavLink
                key={item}
                item={item}
                label={label}
                current={current}
                onClick={handleNavigate}
              />
            ))}
          </div>

          <Link to="/#shop" className="pellier-nav-link lg:hidden">The collection</Link>

          {/* Right: search, persona dropdown, wishlist, bag, surface toggle */}
          <div className="flex items-center gap-1.5 justify-end min-w-0">
            {persona && (
              <div className="hidden xl:block">
                <IconButton
                  icon={<Search className="w-5 h-5" />}
                  ariaLabel="Search: ask Pellier"
                  onClick={handleSearchClick}
                  size="md"
                />
              </div>
            )}

            <PersonaAccountControl chooserOpen={chooserOpen} onOpenChooser={openChooser} />

            <div className="relative">
              <IconButton
                icon={<ShoppingBag className="w-5 h-5" />}
                ariaLabel="Bag"
                onClick={() => setCartOpen(true)}
                size="md"
              />
              {cartItemCount > 0 && (
                <span
                  data-testid="bag-count"
                  className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center text-[10px] font-semibold bg-espresso text-cream-50 pointer-events-none"
                >
                  {cartItemCount}
                </span>
              )}
            </div>

            <button
              ref={menuToggleRef}
              type="button"
              aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
              aria-expanded={mobileMenuOpen}
              aria-controls="pellier-mobile-navigation"
              onClick={() => setMobileMenuOpen(open => !open)}
              className="inline-flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-full text-espresso hover:bg-cream-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 lg:hidden"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
            </button>
          </div>
        </div>

        <AnimatePresence initial={false}>
          {mobileMenuOpen ? (
            <motion.div
              id="pellier-mobile-navigation"
              data-testid="mobile-menu"
              className="
                absolute left-0 right-0 top-full border-b border-sand
                bg-cream px-4 py-3 shadow-warm-md lg:hidden
              "
              initial={
                reduceMotion
                  ? { opacity: 0 }
                  : { opacity: 0, transform: 'translateY(-6px)' }
              }
              animate={
                reduceMotion
                  ? { opacity: 1 }
                  : { opacity: 1, transform: 'translateY(0)' }
              }
              exit={
                reduceMotion
                  ? { opacity: 0 }
                  : { opacity: 0, transform: 'translateY(-6px)' }
              }
              transition={{
                duration: reduceMotion ? 0.12 : 0.18,
                ease: MENU_EASE,
              }}
              style={{ transformOrigin: 'top center' }}
            >
              <div className="grid gap-1">
                {navItems.map(({ item, label }) => (
                  <NavLink
                    key={item}
                    item={item}
                    label={label}
                    current={current}
                    onClick={handleNavigate}
                  />
                ))}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </nav>
      {!persona ? (
        <PersonaModal open={chooserOpen} onClose={() => setChooserOpen(false)} />
      ) : null}
    </header>
  )
}
