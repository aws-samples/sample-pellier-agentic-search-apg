import { apiFetch } from '../services/apiBase'
/**
 * PersonaContext — workshop persona state shared across storefront + Observatory.
 *
 * One source of truth for the active persona. Both the storefront header
 * pill and the Observatory breadcrumb indicator read from this context. The
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
import { type Membership } from '../data/membership'

export interface PersonaSnapshot {
  id: string
  display_name: string
  role_tag: string
  avatar_color: string
  avatar_initial: string
  customer_id: string
  /** Loyalty rung. Presentation only; policy reads Aurora, not this. */
  membership: Membership
  hero_image: string
  hero_alt: string
  hero_subheadline: string
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
  membership: Membership
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
  switchPersona: (personaId: string) => Promise<boolean>
  /**
   * Clear the active shopper identity without rendering a sign-out
   * celebration. Operator client previews use this so client context can never
   * appear inside another shopper's personalized storefront.
   */
  clearPersona: () => void
  /** Sign out — clear the active persona. */
  signOut: () => void
  /** Whether a switch is in flight. */
  switching: boolean
  /** Last live persona-switch failure, surfaced by selection controls. */
  switchError: string | null
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

function clearPersonaStorage(): void {
  try {
    sessionStorage.removeItem(PERSONA_STORAGE_KEY)
  } catch {
    // ignore
  }
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem('pellier-storefront-chat')
  localStorage.removeItem('pellier-observatory-chat')
  localStorage.removeItem('pellier-concierge-storefront')
  localStorage.removeItem('pellier-concierge-observatory')
  localStorage.removeItem('pellier-drawer-storefront')
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
  const [persona, setPersona] = useState<PersonaSnapshot | null>(null)
  const [switching, setSwitching] = useState(false)
  const [switchError, setSwitchError] = useState<string | null>(null)
  const [lastTransition, setLastTransition] = useState<PersonaTransition | null>(null)

  // A session-storage snapshot is only a locator for the durable Aurora
  // session. Rehydrate the persona from the API before presenting it so an
  // old browser value can never masquerade as a current customer record.
  useEffect(() => {
    clearLegacyPersonaPersistence()
    const sessionId = localStorage.getItem(SESSION_KEY)
    if (!sessionId) {
      clearPersonaStorage()
      return
    }

    let active = true
    const controller = new AbortController()
    void apiFetch(`/api/persona/current?session_id=${encodeURIComponent(sessionId)}`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Live persona request failed: ${response.status}`)
        }
        return response.json() as Promise<{ persona: PersonaSnapshot | null }>
      })
      .then((payload) => {
        if (!active) return
        if (payload.persona) {
          setPersona(payload.persona)
        } else {
          clearPersonaStorage()
          setPersona(null)
        }
      })
      .catch((error: unknown) => {
        if (!active || (error as { name?: string })?.name === 'AbortError') return
        // A failed live read is not a license to reuse the local snapshot.
        clearPersonaStorage()
        setPersona(null)
        setSwitchError(
          error instanceof Error
            ? error.message
            : 'The live persona service is unavailable.',
        )
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [])

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
    setSwitchError(null)
    try {
      const res = await apiFetch('/api/persona/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona_id: personaId,
          current_session_id: localStorage.getItem(SESSION_KEY),
        }),
      })
      if (!res.ok) throw new Error(`Switch failed: ${res.status}`)
      const data = await res.json()

      // Store the new session_id so chat picks it up
      localStorage.setItem(SESSION_KEY, data.session_id)

      // Clear any existing chat persistence
      localStorage.removeItem('pellier-storefront-chat')
      localStorage.removeItem('pellier-observatory-chat')
      // Clear retired-modal keys too so a participant moving between source
      // revisions cannot inherit a stale workshop-only thread.
      localStorage.removeItem('pellier-concierge-storefront')
      localStorage.removeItem('pellier-concierge-observatory')
      // ChatDrawer uses its own persist key.
      localStorage.removeItem('pellier-drawer-storefront')

      setPersona(data.persona)
      setLastTransition({
        id: Date.now(),
        kind: 'sign-in',
        persona: data.persona,
      })
      return true
    } catch (err) {
      console.error('Persona switch failed:', err)
      setSwitchError('We couldn’t open that profile. Your current selection is unchanged. Please try again.')
      return false
    } finally {
      setSwitching(false)
    }
  }, [])

  const clearPersona = useCallback(() => {
    setPersona(null)
    clearPersonaStorage()
    setLastTransition(null)
  }, [])

  const signOut = useCallback(() => {
    // Snapshot the current persona BEFORE clearing so the sign-out
    // overlay can greet the right name ("See you soon, Marco").
    const outgoing = persona
    clearPersona()
    if (outgoing) {
      setLastTransition({
        id: Date.now(),
        kind: 'sign-out',
        persona: outgoing,
      })
    }
  }, [clearPersona, persona])

  const clearTransition = useCallback(() => setLastTransition(null), [])

  return (
    <PersonaContext.Provider
      value={{
        persona,
        switchPersona,
        clearPersona,
        signOut,
        switching,
        switchError,
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
