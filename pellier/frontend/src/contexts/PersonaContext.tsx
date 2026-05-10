/**
 * PersonaContext — workshop persona state shared across storefront + Atelier.
 *
 * One source of truth for the active persona. Both the storefront header
 * pill and the Atelier breadcrumb indicator read from this context. The
 * persona modal (shared component, two entry points) writes to it via
 * ``switchPersona()``.
 *
 * State is persisted to localStorage so a page refresh doesn't lose the
 * active persona. Switching personas generates a new session_id and
 * clears the chat.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

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

const STORAGE_KEY = 'pellier-persona'
const SESSION_KEY = 'pellier-session-id'

function loadStored(): PersonaSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<PersonaSnapshot | null>(loadStored)
  const [switching, setSwitching] = useState(false)
  const [lastTransition, setLastTransition] = useState<PersonaTransition | null>(null)

  // Persist to localStorage on change
  useEffect(() => {
    if (persona) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(persona))
    } else {
      localStorage.removeItem(STORAGE_KEY)
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
    } finally {
      setSwitching(false)
    }
  }, [])

  const signOut = useCallback(() => {
    // Snapshot the current persona BEFORE clearing so the sign-out
    // overlay can greet the right name ("See you soon, Marco").
    const outgoing = persona
    setPersona(null)
    localStorage.removeItem(STORAGE_KEY)
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
