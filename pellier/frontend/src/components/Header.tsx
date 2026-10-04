/**
 * Header — the storefront's local row beneath the shared SurfaceNavigation.
 *
 * Shop, Stories and About stay local; the shared bar owns the wordmark, the
 * surface switch, the theme control and the Ask Pellier button. Persona and
 * bag controls preserve their existing interaction and identity boundaries.
 *
 * Visitors without a scenario see a "Select scenario" pill. Once a persona is
 * active, the same header pill opens the shared portrait-led PersonaModal.
 * Neither state is a Cognito sign-in.
 *
 * Copy comes from `copy.ts`. Every color is a token. The row's ground,
 * hairline and stacking are `.pellier-storefront-header` in
 * surface-navigation.css, so the sticky row never depends on a utility.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCart } from '../contexts/CartContext'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { NAV, SCENARIO } from '../copy'
import { Avatar } from '../design/primitives'
import { getPersonaPhoto } from '../data/personaPhotos'
import { IconButton } from '../design/primitives'
import PersonaModal from './PersonaModal'
import {
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
  /** Which nav item is the current page. Defaults to 'home'. */
  current?: NavItem
  /** Optional click handler fired when any nav link is activated. */
  onNavigate?: (item: NavItem) => void
}

/** Storefront destinations. Ask Pellier lives in the shared bar above. */
const NAV_ITEMS: Array<{ item: NavItem; label: string }> = [
  { item: 'shop', label: NAV.SHOP },
  { item: 'stories', label: NAV.STORIES },
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
  const to = item === 'stories' ? '/storyboard' : item === 'about' ? '/about' : '/#shop'
  return (
    <Link
      data-nav-item={item}
      data-current={isCurrent ? 'true' : 'false'}
      aria-current={isCurrent ? 'page' : undefined}
      className="pellier-nav-link"
      to={to}
      onClick={(event) => {
        // Preserve open-in-new-tab and the browser's link menu.
        if (onClick && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && event.button === 0) {
          event.preventDefault()
          onClick(item)
        }
      }}
    >
      {label}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Persona control
// ---------------------------------------------------------------------------

function SignedOutPersonaTrigger({
  open,
  onOpen,
}: {
  open: boolean
  onOpen: () => void
}) {
  // The signed-out pill and the active-persona pill open the same three-card
  // modal, which the header owns.
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="persona-pill"
      className="pellier-account-pill flex min-h-[44px] items-center gap-2 px-3.5 text-[13.5px]"
      aria-label={SCENARIO.SELECT}
      aria-haspopup="dialog"
      aria-expanded={open}
    >
      <UserIcon className="w-4 h-4" aria-hidden />
      <span className="hidden whitespace-nowrap sm:inline">{SCENARIO.SELECT}</span>
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
        className="pellier-account-pill pellier-account-pill-active flex min-h-[44px] items-center gap-2 py-1 pl-1 pr-3 text-[13.5px]"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Avatar
          initial={persona.avatar_initial}
          bgColor={persona.avatar_color}
          photoUrl={getPersonaPhoto(persona.id)}
          size="sm"
        />
        <span className="max-w-[118px] truncate text-[13px] font-medium">
          {persona.display_name}
        </span>
        <ChevronDown size={14} className="opacity-60" aria-hidden />
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

  const handleNavigate = useCallback(
    (item: NavItem) => {
      setMobileMenuOpen(false)
      if (item === 'ask-pellier') {
        openModal('drawer')
        return
      }
      onNavigate?.(item)
    },
    [onNavigate, openModal],
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
      className="pellier-storefront-header"
    >
      <nav
        aria-label="Primary"
        className="relative h-[var(--pellier-storefront-nav-height,56px)] px-[var(--pellier-gutter)]"
      >
        <div className="mx-auto flex h-full items-center justify-between gap-4">
          {/* Left: the storefront's destinations */}
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

          <Link to="/#shop" className="pellier-nav-link whitespace-nowrap lg:hidden">The collection</Link>

          {/* Right: persona, bag, menu */}
          <div className="flex items-center gap-1.5 justify-end min-w-0">
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
                  className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center text-[10px] font-semibold bg-ink text-on-ink pointer-events-none"
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
              className="inline-flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-full text-ink hover:bg-recessed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-copper lg:hidden"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
            </button>
          </div>
        </div>

        <AnimatePresence initial={false}>
          {mobileMenuOpen ? (
            // The page under the open menu is dimmed the way the chooser and
            // the bag dim theirs.
            <motion.div
              key="mobile-navigation-scrim"
              aria-hidden="true"
              data-testid="mobile-menu-scrim"
              className="absolute left-0 right-0 top-full h-[100dvh] bg-ink/20 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduceMotion ? 0.12 : 0.18, ease: MENU_EASE }}
              onClick={() => setMobileMenuOpen(false)}
            />
          ) : null}
          {mobileMenuOpen ? (
            <motion.div
              key="mobile-navigation"
              id="pellier-mobile-navigation"
              data-testid="mobile-menu"
              className="absolute left-0 right-0 top-full border-b border-line bg-page px-4 py-3 shadow-lift lg:hidden"
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
