import { apiFetch } from '../services/apiBase'
/**
 * PersonaContext — workshop persona state shared across the Storefront and the Operator.
 *
 * One source of truth for the active persona. The storefront header
 * pill reads from this context. The
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
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { clearShownTurns } from '../hooks/terminalTurns'

export interface PersonaSnapshot {
  id: string
  /** The catalog grouping the storefront shows this persona, e.g. `house` for Jessica. */
  edit: string
  display_name: string
  role_tag: string
  avatar_color: string
  avatar_initial: string
  /** Null for the signed-out guest, who is not a customer. */
  customer_id: string | null
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
  edit: string
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
  /**
   * Switch to a new persona. Generates a new session, clears chat. A shopper
   * choice passes its sign-in as `signIn`, which runs first, inside the same
   * `switching` span; its errors reach the caller unchanged.
   */
  switchPersona: (personaId: string, signIn?: () => Promise<void>) => Promise<boolean>
  /**
   * Clear the active shopper identity without rendering a sign-out
   * celebration. Operator client previews use this so client context can never
   * appear inside another shopper's personalized storefront.
   */
  clearPersona: () => void
  /** Sign out — clear the active persona. */
  signOut: () => void
  /** Whether a switch, including a shopper choice's sign-in, is in flight. */
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
  /**
   * Start a fresh conversation as the same signed-in shopper: a new server
   * session, the saved thread dropped, the sign-in kept. Resolves false, with
   * the current conversation untouched, when no new session could be had.
   */
  startNewConversation: () => Promise<boolean>
  /** Bumped by each new conversation, so the chat drops the old thread and its turn. */
  conversation: number
  /** The last new-conversation request failed; the old conversation is still open. */
  newConversationFailed: boolean
  /** The shopper carried on in the open conversation, so the failure is old news. */
  clearNewConversationFailed: () => void
}

const PersonaContext = createContext<PersonaContextType | undefined>(undefined)

const PERSONA_STORAGE_KEY = 'pellier-persona'
const SESSION_KEY = 'pellier-session-id'
/** CartContext stamps the bag with the session it belongs to. */
const CART_SESSION_KEY = 'pellier-cart-session'

/**
 * Drop every saved conversation thread. The retired-modal keys go too, so a
 * participant moving between source revisions cannot inherit a stale thread;
 * ChatDrawer uses its own persist key.
 */
function clearSavedThreads(): void {
  localStorage.removeItem('pellier-storefront-chat')
  localStorage.removeItem('pellier-observatory-chat')
  localStorage.removeItem('pellier-concierge-storefront')
  localStorage.removeItem('pellier-concierge-observatory')
  localStorage.removeItem('pellier-drawer-storefront')
}

function clearPersonaStorage(): void {
  try {
    sessionStorage.removeItem(PERSONA_STORAGE_KEY)
  } catch {
    // ignore
  }
  localStorage.removeItem(SESSION_KEY)
  clearShownTurns()
  clearSavedThreads()
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
  const [conversation, setConversation] = useState(0)
  const personaRef = useRef(persona)
  personaRef.current = persona
  const [newConversationFailed, setNewConversationFailed] = useState(false)
  // The mount-time rehydrate answers for the session it started with. A chip click
  // or a sign-out supersedes it, so its late answer must never be applied.
  const rehydrate = useRef<AbortController | null>(null)

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

    const controller = new AbortController()
    rehydrate.current = controller
    const active = () => !controller.signal.aborted
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
        if (!active()) return
        if (payload.persona) {
          setPersona(payload.persona)
        } else {
          clearPersonaStorage()
          setPersona(null)
        }
      })
      .catch((error: unknown) => {
        if (!active() || (error as { name?: string })?.name === 'AbortError') return
        // A failed live read is not a license to reuse the local snapshot.
        clearPersonaStorage()
        setPersona(null)
        setSwitchError(
          error instanceof Error
            ? error.message
            : 'The live persona service is unavailable.',
        )
      })

    return () => controller.abort()
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

  const switchPersona = useCallback(async (personaId: string, signIn?: () => Promise<void>) => {
    setSwitching(true)
    setSwitchError(null)
    // Signing in names the new shopper in the panel before the persona lands, and
    // landing resets the panel's draft and conversation. One span covers both, so
    // nothing typed in between is lost.
    if (signIn) {
      try {
        await signIn()
      } catch (reason) {
        setSwitching(false)
        throw reason
      }
    }
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
      clearSavedThreads()

      rehydrate.current?.abort()
      setNewConversationFailed(false)
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
    rehydrate.current?.abort()
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
  const clearNewConversationFailed = useCallback(() => setNewConversationFailed(false), [])

  // The same endpoint a shopper switch uses issues a fresh session for the same
  // shopper. The sign-in cookie is not touched, so the shopper stays signed in.
  const startNewConversation = useCallback(async (): Promise<boolean> => {
    const current = persona
    if (!current) return false
    const startedFrom = localStorage.getItem(SESSION_KEY)
    setNewConversationFailed(false)
    try {
      const res = await apiFetch('/api/persona/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona_id: current.id, current_session_id: startedFrom }),
      })
      if (!res.ok) throw new Error(`New conversation failed: ${res.status}`)
      const data = (await res.json()) as { session_id?: unknown; persona?: { id?: unknown } | null }
      if (typeof data.session_id !== 'string' || !data.session_id || data.persona?.id !== current.id) {
        throw new Error(`New conversation answered for another session: ${String(data.persona?.id)}`)
      }
      // A sign-out or another shopper landed while this was in flight: theirs stands.
      const superseded = () => localStorage.getItem(SESSION_KEY) !== startedFrom
        || personaRef.current?.id !== current.id
      if (superseded()) return false
      localStorage.setItem(SESSION_KEY, data.session_id)
      if (startedFrom && localStorage.getItem(CART_SESSION_KEY) === startedFrom) {
        localStorage.setItem(CART_SESSION_KEY, data.session_id)
      }
      clearSavedThreads()
      rehydrate.current?.abort()
      setConversation(count => count + 1)
      return true
    } catch (err) {
      console.error('New conversation failed:', err)
      if (localStorage.getItem(SESSION_KEY) === startedFrom && personaRef.current?.id === current.id) {
        setNewConversationFailed(true)
      }
      return false
    }
  }, [persona])

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
        startNewConversation,
        conversation,
        newConversationFailed,
        clearNewConversationFailed,
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
