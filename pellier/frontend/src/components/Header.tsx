/**
 * Header — Boutique sticky header (Phase 2 rebuild).
 *
 * Centered "Pellier" wordmark — Fraunces (`font-display`) + circular P
 * chip; word one step above footer (`text-2xl` vs `text-xl`). Four left
 * nav items (Shop, Stories, Ask Pellier, About), and right cluster: search
 * IconButton, persona Avatar dropdown, wishlist heart IconButton, bag
 * IconButton with count badge, and the Boutique ↔ Atelier surface toggle.
 *
 * The persona Avatar dropdown replaces the old PersonaPill + PersonaModal
 * pattern. It calls `switchPersona` and `signOut` directly from `usePersona()`.
 *
 * Validates Requirements 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 15.3.
 *
 * Copy comes from `copy.ts`. Design tokens from `design/tokens.ts` and
 * Tailwind extended config.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCart } from '../contexts/CartContext'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { NAV } from '../copy'
import { colors } from '../design/tokens'
import { Avatar } from '../design/primitives'
import { getPersonaPhoto } from '../data/personaPhotos'
import { LOCAL_PERSONAS } from '../data/personas'
import { IconButton } from '../design/primitives'
import {
  Search,
  Heart,
  ShoppingBag,
  User as UserIcon,
  ChevronDown,
  LogOut,
} from 'lucide-react'
import SurfaceToggle from './SurfaceToggle'

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

// ---------------------------------------------------------------------------
// Wordmark
// ---------------------------------------------------------------------------

function Wordmark() {
  return (
    <Link
      to="/"
      data-testid="wordmark"
      aria-label={NAV.WORDMARK}
      className="flex items-center gap-2.5 select-none"
    >
      <span
        aria-hidden="true"
        className="pellier-logo-chip bg-espresso text-cream-50"
      >
        P
      </span>
      <span className="font-display text-2xl font-medium tracking-tight text-espresso">
        {NAV.WORDMARK}
      </span>
    </Link>
  )
}

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
  const isCurrent = current === item
  return (
    <button
      type="button"
      data-nav-item={item}
      data-current={isCurrent ? 'true' : 'false'}
      aria-current={isCurrent ? 'page' : undefined}
      onClick={() => onClick?.(item)}
      className={[
        'text-[14px] transition-colors duration-fade ease-out',
        'hover:opacity-70 bg-transparent cursor-pointer',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-espresso focus-visible:ring-offset-2',
        isCurrent ? 'text-espresso font-semibold' : 'text-ink-soft font-normal',
      ].join(' ')}
      style={{
        fontFamily: 'var(--sans)',
        padding: '6px 0',
      }}
    >
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// PersonaDropdown — replaces PersonaPill + PersonaModal
// ---------------------------------------------------------------------------

function PersonaDropdown() {
  const { persona, switchPersona, signOut, switching } = usePersona()
  const [open, setOpen] = useState(false)
  const [personas, setPersonas] = useState<PersonaListItem[]>([])
  const [fetched, setFetched] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch persona list on first open
  useEffect(() => {
    if (!open || fetched) return
    fetch('/api/atelier/personas')
      .then((r) => r.json())
      .then((data) => {
        const list = Array.isArray(data) ? data : []
        // Remove Fresh — signed-out state IS the baseline.
        // Only show Marco, Anna, Theo as selectable personas.
        const withoutFresh = list.filter((p: { id: string }) => p.id !== 'fresh')
        setPersonas(withoutFresh.length > 0 ? withoutFresh : [...LOCAL_PERSONAS])
        setFetched(true)
      })
      .catch(() => {
        setPersonas([...LOCAL_PERSONAS])
        setFetched(true)
      })
  }, [open, fetched])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open])

  const handleSelect = useCallback(
    async (id: string) => {
      await switchPersona(id)
      setOpen(false)
    },
    [switchPersona],
  )

  const handleSignOut = useCallback(() => {
    signOut()
    setOpen(false)
  }, [signOut])

  return (
    <div ref={dropdownRef} className="relative">
      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        data-testid="persona-pill"
        className={[
          'flex items-center gap-2 text-[13.5px] transition-colors duration-fade ease-out',
          'cursor-pointer rounded-full',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-espresso focus-visible:ring-offset-2',
        ].join(' ')}
        style={{
          padding: persona ? '4px 12px 4px 4px' : '7px 14px',
          background: persona ? colors.espresso : 'transparent',
          color: persona ? colors.cream : colors.espresso,
          border: persona
            ? `1px solid ${colors.espresso}`
            : '1px solid rgba(59, 47, 47, 0.18)',
        }}
        aria-expanded={open}
        aria-haspopup="true"
      >
        {persona ? (
          <>
            <Avatar
              initial={persona.avatar_initial}
              bgColor={persona.avatar_color}
              photoUrl={getPersonaPhoto(persona.id)}
              size="sm"
            />
            <span
              className="text-cream-50"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {persona.display_name}
            </span>
            <ChevronDown
              size={14}
              className="text-cream-50 opacity-60"
              aria-hidden
            />
          </>
        ) : (
          <>
            <UserIcon className="w-4 h-4" aria-hidden />
            <span style={{ fontFamily: 'var(--sans)' }}>
              Sign in
            </span>
          </>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          data-testid="persona-dropdown"
          className={[
            'absolute right-0 top-full mt-2 z-50',
            'bg-cream-50 border border-sand rounded-lg shadow-warm-md',
            'min-w-[240px] py-2',
            'transition-opacity duration-fade ease-out',
          ].join(' ')}
          role="menu"
          aria-label="Persona menu"
        >
          {personas.map((p) => {
            const isActive = persona?.id === p.id
            return (
              <button
                key={p.id}
                type="button"
                role="menuitem"
                disabled={switching}
                data-testid={`persona-option-${p.id}`}
                onClick={() => handleSelect(p.id)}
                className={[
                  'w-full flex items-center gap-3 py-2.5 text-left border-l-[3px] transition-colors duration-fade ease-out',
                  'hover:bg-sand/50 cursor-pointer',
                  'focus-visible:outline-none focus-visible:bg-sand/50',
                  isActive
                    ? 'border-espresso bg-[rgba(31,20,16,0.08)] pl-[13px] pr-4'
                    : 'border-transparent pl-[13px] pr-4',
                ].join(' ')}
              >
                <Avatar
                  initial={p.avatar_initial}
                  bgColor={p.avatar_color}
                  photoUrl={getPersonaPhoto(p.id)}
                  size="sm"
                />
                <div className="flex flex-col min-w-0">
                  <span
                    className="text-espresso text-[13px] font-medium truncate"
                    style={{ fontFamily: 'var(--sans)' }}
                  >
                    {p.display_name}
                  </span>
                  <span
                    className="text-ink-soft text-[11px] truncate"
                    style={{ fontFamily: 'var(--sans)' }}
                  >
                    {p.role_tag}
                  </span>
                </div>
              </button>
            )
          })}

          {persona && (
            <>
              <div className="border-t border-sand my-1" />
              <button
                type="button"
                role="menuitem"
                data-testid="persona-sign-out"
                onClick={handleSignOut}
                className={[
                  'w-full flex items-center gap-3 px-4 py-2.5 text-left',
                  'transition-colors duration-fade ease-out',
                  'hover:bg-sand/50 cursor-pointer text-espresso',
                  'focus-visible:outline-none focus-visible:bg-sand/50',
                ].join(' ')}
              >
                <LogOut size={16} className="text-ink-soft" aria-hidden />
                <span
                  className="text-[13px] font-medium"
                  style={{ fontFamily: 'var(--sans)' }}
                >
                  Sign out
                </span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

export default function Header({
  current = 'home',
  onNavigate,
}: HeaderProps) {
  const { items: cartItems, setCartOpen, notify } = useCart()
  const { openModal } = useUI()
  const { persona } = usePersona()
  const cartItemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0)
  const navItems = persona
    ? NAV_ITEMS
    : NAV_ITEMS.filter(({ item }) => item !== 'ask-pellier')

  // The boutique's search is Pellier — the chat drawer. Clicking the
  // Search icon opens the same concierge pill uses, which keeps the
  // header honest: one search surface, two entry points.
  const handleSearchClick = useCallback(() => {
    if (!persona) return
    openModal('drawer')
  }, [persona, openModal])

  // Wishlist isn't wired to a real store (demo scope). Fire a warm
  // toast acknowledging the interaction instead of navigating to a
  // dead route. Honest, non-blocking, matches the Add-to-bag pattern.
  const handleWishlistClick = useCallback(() => {
    notify('Wishlist is coming soon — ask Pellier to hold something for you.')
  }, [notify])

  return (
    <header
      role="banner"
      data-testid="sticky-header"
      className="sticky top-0 z-40 w-full border-b border-sand/50"
      style={{
        background: 'rgba(247, 243, 238, 0.9)',
        WebkitBackdropFilter: 'blur(12px)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <nav
        aria-label="Primary"
        className="relative h-[64px]"
        style={{ padding: '0 clamp(16px, 4vw, 48px)' }}
      >
        {/*
         * Three-column grid:
         *   1fr  | auto | 1fr
         *   left | mark | right
         *
         * The center column hugs the wordmark's intrinsic width; the
         * 1fr left/right columns split remaining space evenly so the
         * wordmark stays visually centered without overlapping either
         * cluster (the previous absolute-positioned approach collided
         * with "About" + the persona pill at narrower desktop widths).
         */}
        <div className="h-full max-w-[1440px] mx-auto grid grid-cols-[1fr_auto_1fr] items-center gap-6">
          {/* Left: four text nav items */}
          <div className="flex items-center gap-6 min-w-0">
            {navItems.map(({ item, label }) => (
              <NavLink
                key={item}
                item={item}
                label={label}
                current={current}
                onClick={onNavigate}
              />
            ))}
          </div>

          {/* Center: wordmark — its own grid track, no absolute positioning */}
          <div data-testid="wordmark-wrapper" className="flex items-center">
            <Wordmark />
          </div>

          {/* Right: search, persona dropdown, wishlist, bag, surface toggle */}
          <div className="flex items-center gap-2 justify-end min-w-0">
            {persona && (
              <IconButton
                icon={<Search className="w-5 h-5" />}
                ariaLabel="Search — ask Pellier"
                onClick={handleSearchClick}
                size="md"
              />
            )}

            <PersonaDropdown />

            <IconButton
              icon={<Heart className="w-5 h-5" />}
              ariaLabel="Wishlist"
              onClick={handleWishlistClick}
              size="md"
            />

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

            <div className="hidden sm:block ml-1">
              <SurfaceToggle />
            </div>
          </div>
        </div>
      </nav>
    </header>
  )
}
