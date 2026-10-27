/**
 * AskShoppers: where a shopper is chosen in the Ask Pellier panel.
 *
 * The four demo customers in lab order (Anna, Marco, Theo, Jessica). Choosing
 * one is the workshop's one-click sign-in with that shopper's demo account,
 * then their edit (`useShopperSignIn`); choosing another signs the previous
 * one out. The shopper shown as signed in is the one the server verified on
 * `/api/auth/me`, never the last click.
 *
 * Signed out, `ShopperCards` fills the panel's empty state with the four
 * shoppers and says the choice is a sign-in and that the signed token, not
 * the choice, is what Pellier trusts. Once a conversation has started the
 * cards give way to `ShopperBar`, one row: the verified shopper (or "Not
 * signed in"), "Switch shopper" (or "Choose a shopper") and, signed in, "Sign
 * out". Opening it unfolds the four choices in a 2×2 grid (they exist only while it is
 * open) and folds again once a sign-in completes. After a choice, on the
 * cards or the chips, focus lands on "Switch shopper".
 *
 * Staff never appear: the list is the four demo shoppers, not the profile
 * read.
 */
import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { ASK_PANEL, HERO_CONCIERGE, REQUESTS_LIMITED, SHOPPER, STATUS_LINES } from '../copy'
import { usePersona } from '../contexts/PersonaContext'
import { getPersonaPhoto } from '../data/personaPhotos'
import { SHOPPER_ORDER, shopperName, useShopperSignIn } from '../hooks/useShopperSignIn'
import { isRequestsLimited, type WorkshopShopper } from '../services/passwordAuth'

function Portrait({ id, size }: { id: WorkshopShopper; size: number }) {
  return (
    <img
      className="cd-who-av"
      src={getPersonaPhoto(id)}
      alt=""
      width={size}
      height={size}
      decoding="async"
    />
  )
}

function SignInErrors({ error }: { error: string | null }) {
  const { switchError } = usePersona()
  return (
    <>
      {/* A plain sentence. The machine code goes to the console. */}
      {error ? (
        <p className="cd-who-alert" role="alert" data-testid="persona-sign-in-error">
          {isRequestsLimited(error) ? REQUESTS_LIMITED : HERO_CONCIERGE.FAILED}
        </p>
      ) : null}
      {switchError ? (
        <p className="cd-who-alert" role="alert">{switchError}</p>
      ) : null}
    </>
  )
}

/**
 * A choice made on the cards replaces them with the bar, so the focused card
 * is gone before the choice finishes. The cards leave this note and the bar
 * reads it when it mounts, so keyboard focus lands on "Switch shopper".
 */
let focusBarAfterChoice = false

/** The choice, shared by the cards and the chips. */
function useChoice(onChosen?: () => void) {
  const { persona, switching } = usePersona()
  const { choose, signOut, busy, error, signedInAs } = useShopperSignIn()
  const pick = (id: WorkshopShopper) => {
    // A sign-in whose edit failed to open can be chosen again.
    if (signedInAs === id && persona?.id === id) return
    if (!onChosen) focusBarAfterChoice = true
    void choose(id).then(ok => {
      if (ok) onChosen?.()
      else focusBarAfterChoice = false
    })
  }
  return { pick, signOut, busy, error, switching, signedInAs }
}

/** Signed out: the four shoppers as cards, with the sign-in note. */
export function ShopperCards() {
  const { pick, busy, error, switching } = useChoice()
  return (
    <div className="cd-shoppers-cards" data-testid="ask-shoppers">
      <div className="cd-who-cards" role="group" aria-label={ASK_PANEL.SIGNED_IN_AS}>
        {SHOPPER_ORDER.map(id => (
          <button
            key={id}
            type="button"
            className="cd-who-card"
            data-testid={`ask-shopper-${id}`}
            aria-busy={busy === id || undefined}
            disabled={Boolean(busy) || switching}
            onClick={() => pick(id)}
          >
            <Portrait id={id} size={40} />
            <span>{busy === id ? HERO_CONCIERGE.SIGNING_IN : shopperName(id)}</span>
          </button>
        ))}
      </div>
      <p className="cd-who-note" data-testid="persona-identity-boundary">
        {HERO_CONCIERGE.IDENTITY_BOUNDARY}
      </p>
      <SignInErrors error={error} />
    </div>
  )
}

/** One row, with the four shoppers a click away. */
export function ShopperBar() {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const switchRef = useRef<HTMLButtonElement>(null)
  const { pick, signOut, busy, error, switching, signedInAs } = useChoice(() => {
    setOpen(false)
    switchRef.current?.focus()
  })

  useEffect(() => {
    if (!focusBarAfterChoice) return
    focusBarAfterChoice = false
    switchRef.current?.focus()
  }, [])

  return (
    <div className="cd-shoppers" data-testid="ask-shoppers">
      <div className="cd-who-row" role="group" aria-label={ASK_PANEL.SIGNED_IN_AS}>
        {signedInAs ? <Portrait id={signedInAs} size={28} /> : null}
        <span className="cd-who-name" data-testid="ask-signed-in-name">
          {signedInAs ? shopperName(signedInAs) : STATUS_LINES.NOT_SIGNED_IN}
        </span>
        <button
          ref={switchRef}
          type="button"
          className="cd-who-switch"
          data-testid="ask-switch-shopper"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => setOpen(value => !value)}
        >
          {signedInAs ? ASK_PANEL.SWITCH : SHOPPER.CHOOSE}
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        {signedInAs ? (
          <button
            type="button"
            className="cd-who-signout"
            data-testid="ask-sign-out"
            onClick={signOut}
          >
            {SHOPPER.SIGN_OUT}
          </button>
        ) : null}
      </div>
      {open ? (
        <div id={panelId} className="cd-who">
          {SHOPPER_ORDER.map(id => (
            <button
              key={id}
              type="button"
              className="cd-who-chip"
              data-testid={`ask-shopper-${id}`}
              aria-pressed={signedInAs === id}
              aria-busy={busy === id || undefined}
              disabled={Boolean(busy) || switching}
              onClick={() => pick(id)}
            >
              <Portrait id={id} size={40} />
              {busy === id ? HERO_CONCIERGE.SIGNING_IN : shopperName(id)}
            </button>
          ))}
        </div>
      ) : null}
      {!signedInAs && open ? (
        <p className="cd-who-note" data-testid="persona-identity-boundary">
          {HERO_CONCIERGE.IDENTITY_BOUNDARY}
        </p>
      ) : null}
      <SignInErrors error={error} />
    </div>
  )
}
