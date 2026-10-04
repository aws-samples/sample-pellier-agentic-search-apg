/**
 * "Signed in as": one chip per provisioned shopper.
 *
 * A workshop convenience, not a production pattern. Each chip performs a real
 * Cognito sign-in on the server with the provisioned test credentials and
 * sets the same session the sign-in page sets, then selects that shopper's
 * scenario so the store and the conversation follow. Jessica has no scenario
 * of her own, so her chip keeps the neutral one; her verified identity is
 * what the turn binds to. Staff never get a chip: Nadia signs in on the
 * Operator desk with her password.
 */
import { useEffect, useRef, useState } from 'react'
import { useOptionalAuth } from '../contexts/AuthContext'
import { usePersona } from '../contexts/PersonaContext'
import { WORKSHOP_SIGN_IN } from '../copy'
import { getPersonaPhoto } from '../data/personaPhotos'
import { PasswordAuthError, workshopSignIn, type WorkshopShopper } from '../services/passwordAuth'

/** The shoppers with a scenario row to select after signing in. */
const SCENARIO_FOR: Record<WorkshopShopper, string> = {
  anna: 'anna',
  marco: 'marco',
  theo: 'theo',
  jessica: 'fresh',
}

interface WorkshopSignInProps {
  /** Called after a chip has signed in and selected its scenario. */
  onSignedIn?: () => void
  className?: string
}

export default function WorkshopSignIn({ onSignedIn, className }: WorkshopSignInProps) {
  const auth = useOptionalAuth()
  const { switchPersona } = usePersona()
  const [busy, setBusy] = useState<WorkshopShopper | null>(null)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const active = auth?.isAuthenticated ? (auth.user?.username ?? '').toLowerCase() : ''

  async function signInAs(id: WorkshopShopper) {
    if (busy) return
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setBusy(id)
    setError(null)
    try {
      await workshopSignIn(id, abort.signal)
      await auth?.refresh()
      await switchPersona(SCENARIO_FOR[id])
      onSignedIn?.()
    } catch (reason) {
      if (abort.signal.aborted) return
      setError(reason instanceof PasswordAuthError ? reason.message : 'auth_unavailable')
    } finally {
      if (!abort.signal.aborted) setBusy(null)
    }
  }

  return (
    <div className={['cd-workshop', className ?? ''].filter(Boolean).join(' ')} data-testid="workshop-sign-in">
      <div className="cd-workshop-row">
        <span className="cd-workshop-label">{WORKSHOP_SIGN_IN.LABEL}</span>
        <div className="cd-workshop-chips" role="group" aria-label={WORKSHOP_SIGN_IN.LABEL}>
          {WORKSHOP_SIGN_IN.shoppers.map(shopper => {
            const pressed = active === shopper.id
            const photo = getPersonaPhoto(shopper.id)
            return (
              <button
                key={shopper.id}
                type="button"
                className="cd-workshop-chip"
                aria-pressed={pressed}
                aria-busy={busy === shopper.id || undefined}
                disabled={Boolean(busy)}
                onClick={() => void signInAs(shopper.id)}
                data-testid={`workshop-sign-in-${shopper.id}`}
              >
                {photo ? <img src={photo} alt="" aria-hidden="true" /> : null}
                <span>{busy === shopper.id ? WORKSHOP_SIGN_IN.SIGNING_IN : shopper.name}</span>
              </button>
            )
          })}
        </div>
        {auth?.isAuthenticated ? (
          <button type="button" className="cd-workshop-signout" onClick={auth.logout}>
            {WORKSHOP_SIGN_IN.SIGN_OUT}
          </button>
        ) : null}
      </div>
      {error ? (
        <p className="cd-workshop-error" role="alert">
          {WORKSHOP_SIGN_IN.FAILED} <code>{error}</code>
        </p>
      ) : null}
      <p className="cd-workshop-note">{WORKSHOP_SIGN_IN.NOTE}</p>
    </div>
  )
}
