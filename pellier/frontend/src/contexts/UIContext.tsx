/**
 * UI Context — Centralizes cross-component UI coordination.
 *
 * Two concerns live here:
 *
 *  1. Modal singleton (Req 1.11.2 through 1.11.5): every overlay surface in
 *     the storefront (concierge, auth, preferences, cart, checkout) is
 *     coordinated through `activeModal`. Opening any modal closes the
 *     previous one first so only one is ever visible. A single global
 *     keydown handler lives in `UIProvider` so every route inherits the
 *     same shortcuts: Cmd+K / Ctrl+K toggles the concierge, Escape closes
 *     whichever modal is active.
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
  | 'concierge'
  | 'drawer'
  | 'auth'
  | 'preferences'
  | 'cart'
  | 'checkout'
  | 'comparison'

export type ActiveModal = ModalName | null

/**
 * Minimal product shape understood by ProductComparison. We keep the fields
 * loose so the concierge can hand off to the comparison modal without
 * importing chat types into this context. ComparisonHost casts this back to
 * ChatProduct at the render boundary.
 */
export interface ComparisonProduct {
  id: number
  name: string
  price: number
  image?: string
  category?: string
  rating?: number
  reviews?: number
}

interface UIContextValue {
  // Modal singleton
  activeModal: ActiveModal
  openModal: (name: ModalName) => void
  closeModal: () => void
  toggleConcierge: () => void

  // Chat drawer (storefront-only surface). Route-aware components call
  // ``setChatSurface('drawer')`` on mount so the global ⌘K handler
  // opens the right surface without needing useLocation() in UIProvider.
  chatSurface: 'concierge' | 'drawer'
  setChatSurface: (s: 'concierge' | 'drawer') => void
  toggleDrawer: () => void
  openDrawerWithQuery: (text: string) => void

  // Pending concierge query — the hero search pill seeds this when the
  // user submits, then ConciergeModal/ChatDrawer consumes it on open
  // (and clears it via `consumePendingQuery`). Keeps the handoff
  // one-way so the hero form doesn't also need to hold onto the value.
  pendingConciergeQuery: string | null
  openConciergeWithQuery: (text: string) => void
  consumePendingQuery: () => string | null

  // Comparison payload — set when opening the comparison modal so the
  // receiver can render the product list without prop-drilling. The concierge
  // closes, comparison opens with this payload, and when the user dismisses
  // comparison we restore the concierge (useAgentChat preserves chat state).
  comparisonProducts: ComparisonProduct[]
  openComparison: (products: ComparisonProduct[]) => void

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
  const [activeModal, setActiveModal] = useState<ActiveModal>(null)
  const [comparisonProducts, setComparisonProducts] = useState<
    ComparisonProduct[]
  >([])
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
  // BoutiquePage sets 'drawer'; WorkshopPage sets 'concierge'.
  const [chatSurface, setChatSurface] = useState<'concierge' | 'drawer'>('drawer')

  const openModal = useCallback((name: ModalName) => {
    // Opening any modal closes the previous one first (Req 1.11.4).
    setActiveModal(name)
  }, [])

  const closeModal = useCallback(() => {
    setActiveModal(prev => {
      // Closing the comparison modal restores the concierge so the user
      // can continue the conversation they triggered Compare from.
      // `useAgentChat` preserves the chat state across this transition
      // because its state lives in the hook, not the modal DOM.
      if (prev === 'comparison') return 'concierge'
      return null
    })
  }, [])

  const toggleConcierge = useCallback(() => {
    setActiveModal(prev => (prev === 'concierge' ? null : 'concierge'))
  }, [])

  const toggleDrawer = useCallback(() => {
    setActiveModal(prev => (prev === 'drawer' ? null : 'drawer'))
  }, [])

  const openComparison = useCallback((products: ComparisonProduct[]) => {
    setComparisonProducts(products)
    setActiveModal('comparison')
  }, [])

  const openConciergeWithQuery = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    pendingQueryRef.current = trimmed
    setPendingConciergeQuery(trimmed)
    setActiveModal('concierge')
  }, [])

  const openDrawerWithQuery = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    pendingQueryRef.current = trimmed
    setPendingConciergeQuery(trimmed)
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
      // Cmd+K on macOS, Ctrl+K elsewhere: toggle the active chat surface.
      // ``chatSurface`` is set by route-aware components (BoutiquePage
      // sets 'drawer', WorkshopPage sets 'concierge') so this handler
      // doesn't need useLocation().
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        const target = chatSurface
        setActiveModal(prev => (prev === target ? null : target))
        return
      }
      // Escape: close comparison back to concierge, or close whichever other
      // modal is active (no-op when none is open).
      if (e.key === 'Escape') {
        setActiveModal(prev => {
          if (prev === 'comparison') return 'concierge'
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
      toggleConcierge,
      chatSurface,
      setChatSurface,
      toggleDrawer,
      openDrawerWithQuery,
      pendingConciergeQuery,
      openConciergeWithQuery,
      consumePendingQuery,
      comparisonProducts,
      openComparison,
      openChat,
      announcementDismissed,
      dismissAnnouncement,
    }),
    [
      activeModal,
      openModal,
      closeModal,
      toggleConcierge,
      chatSurface,
      setChatSurface,
      toggleDrawer,
      openDrawerWithQuery,
      pendingConciergeQuery,
      openConciergeWithQuery,
      consumePendingQuery,
      comparisonProducts,
      openComparison,
      openChat,
      announcementDismissed,
      dismissAnnouncement,
    ],
  )

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>
}
