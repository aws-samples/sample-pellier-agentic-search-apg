/**
 * Choosing a shopper signs in with their demo account. One way in.
 *
 * The home chooser and the header's switcher both call `choose`, which does
 * three things in order: the workshop sign-in (a real Cognito sign-in on the
 * server, for the four demo shoppers only; choosing another shopper revokes
 * the previous one's session there), a fresh read of the verified session,
 * and then the shopper's storefront edit. The edit follows the sign-in and
 * never the other way round: Pellier trusts the signed token, not the choice.
 *
 * A workshop convenience, not a production pattern. Nadia, the staff member,
 * is never offered here: she signs in with her password on the Operator desk.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useOptionalAuth } from '../contexts/AuthContext'
import { usePersona } from '../contexts/PersonaContext'
import {
  PasswordAuthError,
  WORKSHOP_SHOPPERS,
  workshopSignIn,
  type WorkshopShopper,
} from '../services/passwordAuth'

/** The four customers, in the order the chooser shows them. */
export const SHOPPER_ORDER: readonly WorkshopShopper[] = ['marco', 'anna', 'theo', 'jessica']

export function isWorkshopShopper(id: string): id is WorkshopShopper {
  return (WORKSHOP_SHOPPERS as readonly string[]).includes(id)
}

/** Only the four demo shoppers, in chooser order, whatever else a list holds. */
export function chooserShoppers<T extends { id: string }>(profiles: readonly T[]): T[] {
  return SHOPPER_ORDER.flatMap(id => profiles.filter(profile => profile.id === id))
}

export interface ShopperSignIn {
  /** Sign the chosen shopper in, then select their edit. Resolves true on success. */
  choose: (id: WorkshopShopper) => Promise<boolean>
  /** Sign out: back to the neutral new-visitor store. */
  signOut: () => void
  /** The shopper being signed in, while a choice is in flight. */
  busy: WorkshopShopper | null
  /** The machine-readable reason the last choice failed. */
  error: string | null
  /** The verified shopper this session belongs to, from the server. */
  signedInAs: WorkshopShopper | null
}

export function useShopperSignIn(): ShopperSignIn {
  const auth = useOptionalAuth()
  const { switchPersona, signOut: clearShopper } = usePersona()
  const [busy, setBusy] = useState<WorkshopShopper | null>(null)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const choose = useCallback(async (id: WorkshopShopper) => {
    if (busy) return false
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setBusy(id)
    setError(null)
    try {
      await workshopSignIn(id, abort.signal)
      await auth?.refresh()
      return await switchPersona(id)
    } catch (reason) {
      if (abort.signal.aborted) return false
      setError(reason instanceof PasswordAuthError ? reason.message : 'auth_unavailable')
      return false
    } finally {
      if (!abort.signal.aborted) setBusy(null)
    }
  }, [auth, busy, switchPersona])

  const signOut = useCallback(() => {
    clearShopper()
    auth?.logout()
  }, [auth, clearShopper])

  const username = auth?.isAuthenticated ? (auth.user?.username ?? '').toLowerCase() : ''
  return {
    choose,
    signOut,
    busy,
    error,
    signedInAs: isWorkshopShopper(username) ? username : null,
  }
}

/**
 * Signed out is the neutral new-visitor store.
 *
 * A shopper's edit restored from an earlier visit, after the session ended
 * (an expired token, a sign-out in another tab), is cleared once the server
 * says the session is anonymous. A failed check clears nothing: unavailable
 * is not signed out.
 */
export function useNeutralWhenSignedOut(): void {
  const auth = useOptionalAuth()
  const { persona, clearPersona } = usePersona()
  const anonymous = Boolean(auth && !auth.loading && !auth.authUnavailable && !auth.isAuthenticated)
  useEffect(() => {
    if (anonymous && persona) clearPersona()
  }, [anonymous, persona, clearPersona])
}
