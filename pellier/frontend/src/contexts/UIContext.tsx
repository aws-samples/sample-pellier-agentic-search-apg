/**
 * UI Context — Centralizes cross-component UI coordination.
 *
 * Two concerns live here:
 *
 *  1. Modal singleton (Req 1.11.2 through 1.11.5): every overlay surface in
 *     the storefront (drawer, auth, cart) is
 *     coordinated through `activeModal`. Opening any modal closes the
 *     previous one first so only one is ever visible. A single global
 *     keydown handler lives in `UIProvider` so every route inherits the
 *     same shortcuts: Cmd+K / Ctrl+K toggles the storefront drawer, Escape closes
 *     whichever modal is active.
 *
 *     On a desktop width the storefront opens with Ask Pellier docked
 *     beside it (`activeModal === 'drawer'`). Closing the panel is
 *     remembered until the page reloads, so moving between storefront
 *     pages does not open it again; the Operator and the sign-in page never
 *     open it by themselves.
 *
 *  2. Legacy helpers kept for the existing Lab UI (AIAssistant + App):
 *     `openChat()` centralizes the `document.querySelector('[data-tour="chat-bubble"]')`
 *     pattern; `announcementDismissed` / `dismissAnnouncement` track the
 *     per-mode announcement banner state.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { WorkshopMode } from './LayoutContext'

export type ModalName =
  | 'drawer'
  | 'auth'
  | 'cart'

export type ActiveModal = ModalName | null
export type ChatSurface = 'drawer' | 'none'

/** From this width Ask Pellier docks beside the store; below it, it stacks under the page. */
export const DOCK_MIN_WIDTH = 1080
const DOCK_MEDIA = `(min-width: ${DOCK_MIN_WIDTH}px)`

export function docksBesideStore(): boolean {
  if (typeof window === 'undefined') return true
  return window.innerWidth >= DOCK_MIN_WIDTH
}

/** Whether the panel sits beside the page right now, following resizes. */
export function useDocksBesideStore(): boolean {
  const [docked, setDocked] = useState(docksBesideStore)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia(DOCK_MEDIA)
    const sync = () => setDocked(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])
  return docked
}

/** The storefront opens docked; the Operator and the sign-in page are surfaces of their own. */
export function opensDockOn(pathname: string): boolean {
  return !/\/(operator|signin)(\/|$)/.test(pathname)
}

function initialModal(): ActiveModal {
  if (typeof window === 'undefined') return null
  return docksBesideStore() && opensDockOn(window.location.pathname) ? 'drawer' : null
}

interface UIContextValue {
  // Modal singleton
  activeModal: ActiveModal
  openModal: (name: ModalName) => void
  closeModal: () => void
  /** The shopper closed Ask Pellier: it stays closed until they open it again. */
  dismissDrawer: () => void
  /** On a storefront page at a desktop width, dock Ask Pellier unless the shopper closed it. */
  restoreDock: () => void
  /**
   * Whether the shopper opened the panel (a button, a question, the
   * shortcut), as opposed to the store docking it by default. Only an open
   * the shopper asked for moves focus into the composer.
   */
  drawerOpenedByShopper: () => boolean

  // Chat is a storefront-only surface. Dedicated operational and evidence
  // routes set this to `none`, leaving their keyboard conventions untouched.
  chatSurface: ChatSurface
  setChatSurface: (s: ChatSurface) => void
  toggleDrawer: () => void
  openDrawerWithQuery: (text: string) => void

  // Pending shopper query — the hero search pill seeds this when the
  // user submits, then ChatDrawer consumes it on open
  // (and clears it via `consumePendingQuery`). Keeps the handoff
  // one-way so the hero form doesn't also need to hold onto the value.
  pendingConciergeQuery: string | null
  consumePendingQuery: () => string | null

  // Whether an Ask Pellier turn is running. The header's Ask Pellier button
  // pulses its copper dot only while this is true (signature element 2); the
  // drawer reports it from the chat hook's loading state.
  turnRunning: boolean
  setTurnRunning: (running: boolean) => void

  // Legacy helpers (preserved for existing consumers)
  openChat: () => void
  announcementDismissed: Record<WorkshopMode, boolean>
  dismissAnnouncement: (mode: WorkshopMode) => void
}

const UIContext = createContext<UIContextValue | undefined>(undefined)

export function useUI() {
  const ctx = useContext(UIContext)
  if (!ctx) throw new Error('useUI must be used within UIProvider')
  return ctx
}

export function UIProvider({ children }: { children: ReactNode }) {
  // --- Modal singleton -----------------------------------------------------
  const [activeModal, setActiveModal] = useState<ActiveModal>(initialModal)
  const drawerDismissed = useRef(false)
  const openedByShopper = useRef(false)
  // Ref mirror for synchronous reads — React 18 batches state updates,
  // so setPendingConciergeQuery's updater may not run synchronously.
  // The ref is always in sync so consumePendingQuery can read it
  // immediately inside useLayoutEffect.
  const pendingQueryRef = useRef<string | null>(null)
  const [pendingConciergeQuery, setPendingConciergeQuery] = useState<
    string | null
  >(null)

  // Chat surface preference — route-aware components set this on mount
  // so the global ⌘K handler opens the right surface without needing
  // useLocation() (UIProvider sits above BrowserRouter).
  const [chatSurface, setChatSurface] = useState<ChatSurface>('drawer')
  const [turnRunning, setTurnRunning] = useState(false)

  const openModal = useCallback((name: ModalName) => {
    // Opening any modal closes the previous one first (Req 1.11.4).
    if (name === 'drawer') {
      drawerDismissed.current = false
      openedByShopper.current = true
    }
    setActiveModal(name)
  }, [])

  const closeModal = useCallback(() => {
    setActiveModal(null)
  }, [])

  const dismissDrawer = useCallback(() => {
    drawerDismissed.current = true
    setActiveModal(prev => (prev === 'drawer' ? null : prev))
  }, [])

  const restoreDock = useCallback(() => {
    if (drawerDismissed.current || !docksBesideStore()) return
    setActiveModal(prev => {
      if (prev) return prev
      openedByShopper.current = false
      return 'drawer'
    })
  }, [])

  const drawerOpenedByShopper = useCallback(() => openedByShopper.current, [])

  const toggleDrawer = useCallback(() => {
    setActiveModal(prev => {
      drawerDismissed.current = prev === 'drawer'
      openedByShopper.current = true
      return prev === 'drawer' ? null : 'drawer'
    })
  }, [])

  const openDrawerWithQuery = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    pendingQueryRef.current = trimmed
    setPendingConciergeQuery(trimmed)
    drawerDismissed.current = false
    openedByShopper.current = true
    setActiveModal('drawer')
  }, [])

  // Read-and-clear. Uses the ref for a synchronous read so
  // useLayoutEffect in ChatDrawer gets the value immediately,
  // even when React 18 batches the state update.
  const consumePendingQuery = useCallback(() => {
    const value = pendingQueryRef.current
    pendingQueryRef.current = null
    setPendingConciergeQuery(null)
    return value
  }, [])

  // Global keyboard shortcuts (Req 1.11.2, 1.11.3, 1.11.5).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Cmd+K on macOS, Ctrl+K elsewhere: toggle the storefront chat surface.
      // ``chatSurface`` is set by route-aware components (PellierPage
      // sets 'drawer' on mount) so this handler doesn't need useLocation().
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        // Operational and evidence routes own their own keyboard model. Do
        // not swallow the browser shortcut for a chat surface that is absent.
        if (chatSurface === 'none') return
        e.preventDefault()
        setActiveModal(prev => {
          drawerDismissed.current = prev === 'drawer'
          openedByShopper.current = true
          return prev === 'drawer' ? null : 'drawer'
        })
        return
      }
      // Escape: close whichever modal is active (no-op when none is open).
      if (e.key === 'Escape') {
        setActiveModal(prev => {
          if (prev === 'drawer') drawerDismissed.current = true
          return null
        })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [chatSurface])

  // --- Legacy helpers ------------------------------------------------------
  // AIAssistant owns its local isOpen state and syncs outward to LayoutContext.
  // There is no inbound signal to set AIAssistant's isOpen from outside,
  // so we click the bubble element. This centralizes the DOM query to one place.
  const openChat = useCallback(() => {
    const bubble = document.querySelector('[data-tour="chat-bubble"]') as HTMLElement | null
    if (bubble) bubble.click()
  }, [])

  // Announcement banner dismissal — per-mode, React state only (not localStorage).
  const [announcementDismissed, setAnnouncementDismissed] = useState<
    Record<WorkshopMode, boolean>
  >({
    legacy: false,
    search: false,
    agentic: false,
    production: false,
  })

  const dismissAnnouncement = useCallback((mode: WorkshopMode) => {
    setAnnouncementDismissed(prev => ({ ...prev, [mode]: true }))
  }, [])

  const value = useMemo<UIContextValue>(
    () => ({
      activeModal,
      openModal,
      closeModal,
      dismissDrawer,
      restoreDock,
      drawerOpenedByShopper,
      chatSurface,
      setChatSurface,
      toggleDrawer,
      openDrawerWithQuery,
      pendingConciergeQuery,
      consumePendingQuery,
      turnRunning,
      setTurnRunning,
      openChat,
      announcementDismissed,
      dismissAnnouncement,
    }),
    [
      activeModal,
      openModal,
      closeModal,
      dismissDrawer,
      restoreDock,
      drawerOpenedByShopper,
      chatSurface,
      setChatSurface,
      toggleDrawer,
      openDrawerWithQuery,
      pendingConciergeQuery,
      consumePendingQuery,
      turnRunning,
      openChat,
      announcementDismissed,
      dismissAnnouncement,
    ],
  )

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>
}
