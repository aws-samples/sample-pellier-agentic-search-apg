/**
 * PersonaContext — workshop persona state shared across storefront + Atelier.
 *
 * One source of truth for the active persona. Both the storefront header
 * pill and the Atelier breadcrumb indicator read from this context. The
 * persona modal (shared component, two entry points) writes to it via
 * ``switchPersona()``.
 *
 * State is persisted to **sessionStorage** (not localStorage) so a fresh
 * browser tab or workshop box starts signed out, while an in-tab refresh
 * keeps the persona the participant selected. Switching personas generates
 * a new session_id and clears the chat.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { LOCAL_PERSONAS } from '../data/personas'

export interface PersonaSnapshot {
  id: string
  display_name: string
  role_tag: string
  avatar_color: string
  avatar_initial: string
  customer_id: string
  stats: {
    visits: number
    orders: number
    last_seen_days: number | null
  }
}

export interface PersonaListItem {
  id: string
  display_name: string
  role_tag: string
  blurb: string
  avatar_color: string
  avatar_initial: string
  stats: {
    visits: number
    orders: number
    last_seen_days: number | null
  }
}

/**
 * Marker for the most recent persona transition. Bumped on sign-in
 * and sign-out so overlay components can render a brief celebration
 * without needing their own state machine. Bumps monotonically via
 * `id` so a re-sign-in to the same persona still triggers a new
 * overlay.
 */
export interface PersonaTransition {
  /** Monotonic counter — changes even when the persona doesn't. */
  id: number
  kind: 'sign-in' | 'sign-out'
  /** The persona that just signed in, or the one that just signed out. */
  persona: PersonaSnapshot
}

interface PersonaContextType {
  /** The active persona, or null if none selected. */
  persona: PersonaSnapshot | null
  /** Switch to a new persona. Generates a new session, clears chat. */
  switchPersona: (personaId: string) => Promise<void>
  /** Sign out — clear the active persona. */
  signOut: () => void
  /** Whether a switch is in flight. */
  switching: boolean
  /** The most recent sign-in or sign-out event, or null if none has
   * happened in this session. Consumers can read this to render a
   * transient celebration. */
  lastTransition: PersonaTransition | null
  /** Clear the transition marker — called by the overlay after its
   * dismissal timer fires, so stale markers don't re-trigger on
   * remount. */
  clearTransition: () => void
}

const PersonaContext = createContext<PersonaContextType | undefined>(undefined)

const PERSONA_STORAGE_KEY = 'pellier-persona'
const SESSION_KEY = 'pellier-session-id'

function loadStoredPersona(): PersonaSnapshot | null {
  try {
    const raw = sessionStorage.getItem(PERSONA_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** Drop pre-3.2 localStorage persona so shared boxes don't reopen as Marco. */
function clearLegacyPersonaPersistence(): void {
  try {
    localStorage.removeItem(PERSONA_STORAGE_KEY)
  } catch {
    // private mode — ignore
  }
}

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<PersonaSnapshot | null>(() => {
    clearLegacyPersonaPersistence()
    return loadStoredPersona()
  })
  const [switching, setSwitching] = useState(false)
  const [lastTransition, setLastTransition] = useState<PersonaTransition | null>(null)

  // Persist to sessionStorage on change (tab-scoped; fresh tab = signed out).
  useEffect(() => {
    try {
      if (persona) {
        sessionStorage.setItem(PERSONA_STORAGE_KEY, JSON.stringify(persona))
      } else {
        sessionStorage.removeItem(PERSONA_STORAGE_KEY)
      }
    } catch {
      // quota / private mode — in-memory state still works for this visit
    }
  }, [persona])

  const switchPersona = useCallback(async (personaId: string) => {
    setSwitching(true)
    try {
      const res = await fetch('/api/persona/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona_id: personaId }),
      })
      if (!res.ok) throw new Error(`Switch failed: ${res.status}`)
      const data = await res.json()

      // Store the new session_id so chat picks it up
      localStorage.setItem(SESSION_KEY, data.session_id)

      // Clear any existing chat persistence
      localStorage.removeItem('pellier-storefront-chat')
      localStorage.removeItem('pellier-atelier-chat')
      // ConciergeModal uses its own persist keys — clear those too so the
      // personalized welcome ("Good evening, Marco") actually renders on
      // the next open instead of being shadowed by a stale cached reply.
      localStorage.removeItem('pellier-concierge-storefront')
      localStorage.removeItem('pellier-concierge-atelier')
      // ChatDrawer uses its own persist key.
      localStorage.removeItem('pellier-drawer-storefront')

      setPersona(data.persona)
      setLastTransition({
        id: Date.now(),
        kind: 'sign-in',
        persona: data.persona,
      })
    } catch (err) {
      console.error('Persona switch failed:', err)
      const fallback = LOCAL_PERSONAS.find((p) => p.id === personaId)
      if (!fallback) return

      const fallbackPersona: PersonaSnapshot = {
        id: fallback.id,
        display_name: fallback.display_name,
        role_tag: fallback.role_tag,
        avatar_color: fallback.avatar_color,
        avatar_initial: fallback.avatar_initial,
        customer_id: fallback.customer_id,
        stats: fallback.stats,
      }

      localStorage.setItem(SESSION_KEY, `local-${fallback.id}-${Date.now()}`)
      localStorage.removeItem('pellier-storefront-chat')
      localStorage.removeItem('pellier-atelier-chat')
      localStorage.removeItem('pellier-concierge-storefront')
      localStorage.removeItem('pellier-concierge-atelier')
      localStorage.removeItem('pellier-drawer-storefront')

      setPersona(fallbackPersona)
      setLastTransition({
        id: Date.now(),
        kind: 'sign-in',
        persona: fallbackPersona,
      })
    } finally {
      setSwitching(false)
    }
  }, [])

  const signOut = useCallback(() => {
    // Snapshot the current persona BEFORE clearing so the sign-out
    // overlay can greet the right name ("See you soon, Marco").
    const outgoing = persona
    setPersona(null)
    try {
      sessionStorage.removeItem(PERSONA_STORAGE_KEY)
    } catch {
      // ignore
    }
    localStorage.removeItem(SESSION_KEY)
    localStorage.removeItem('pellier-storefront-chat')
    localStorage.removeItem('pellier-atelier-chat')
    localStorage.removeItem('pellier-concierge-storefront')
    localStorage.removeItem('pellier-concierge-atelier')
    localStorage.removeItem('pellier-drawer-storefront')
    if (outgoing) {
      setLastTransition({
        id: Date.now(),
        kind: 'sign-out',
        persona: outgoing,
      })
    }
  }, [persona])

  const clearTransition = useCallback(() => setLastTransition(null), [])

  return (
    <PersonaContext.Provider
      value={{
        persona,
        switchPersona,
        signOut,
        switching,
        lastTransition,
        clearTransition,
      }}
    >
      {children}
    </PersonaContext.Provider>
  )
}

export function usePersona() {
  const ctx = useContext(PersonaContext)
  if (!ctx) throw new Error('usePersona must be used within PersonaProvider')
  return ctx
}
