/**
 * AskShoppers: "Signed in as" at the top of the Ask Pellier panel.
 *
 * The four customers in lab order (Anna, Marco, Theo, Jessica), each a chip
 * with a small round portrait. Choosing one is the workshop's one-click
 * sign-in with that shopper's demo account, then their edit
 * (`useShopperSignIn`); choosing another signs the previous one out. The
 * selected chip is the shopper the server verified on `/api/auth/me`, never
 * the last click. Once someone is signed in, "Sign out" at the end of the
 * row returns to the neutral, signed-out store.
 *
 * Staff never appear: the list is the four demo shoppers, not the profile
 * read. The line under the chips says the choice is a sign-in and that the
 * signed token, not this choice, is what Pellier trusts.
 */
import { ASK_PANEL, HERO_CONCIERGE, SHOPPER } from '../copy'
import { usePersona } from '../contexts/PersonaContext'
import { getPersonaPhoto } from '../data/personaPhotos'
import { SHOPPER_ORDER, shopperName, useShopperSignIn } from '../hooks/useShopperSignIn'

export default function AskShoppers() {
  const { persona, switching, switchError } = usePersona()
  const { choose, signOut, busy, error, signedInAs } = useShopperSignIn()

  return (
    <div className="cd-shoppers" data-testid="ask-shoppers">
      <div className="cd-who" role="group" aria-label={ASK_PANEL.SIGNED_IN_AS}>
        <span className="cd-who-label" aria-hidden="true">{ASK_PANEL.SIGNED_IN_AS}</span>
        {SHOPPER_ORDER.map(id => {
          const selected = signedInAs === id
          return (
            <button
              key={id}
              type="button"
              className="cd-who-chip"
              data-testid={`ask-shopper-${id}`}
              aria-pressed={selected}
              aria-busy={busy === id || undefined}
              disabled={Boolean(busy) || switching}
              onClick={() => {
                // A sign-in whose edit failed to open can be chosen again.
                if (selected && persona?.id === id) return
                void choose(id)
              }}
            >
              <img
                className="cd-who-av"
                src={getPersonaPhoto(id)}
                alt=""
                width={24}
                height={24}
                decoding="async"
              />
              {busy === id ? HERO_CONCIERGE.SIGNING_IN : shopperName(id)}
            </button>
          )
        })}
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
      <p className="cd-who-note" data-testid="persona-identity-boundary">
        {HERO_CONCIERGE.IDENTITY_BOUNDARY}
      </p>
      {/* A plain sentence. The machine code goes to the console. */}
      {error ? (
        <p className="cd-who-alert" role="alert" data-testid="persona-sign-in-error">
          {HERO_CONCIERGE.FAILED}
        </p>
      ) : null}
      {switchError ? (
        <p className="cd-who-alert" role="alert">{switchError}</p>
      ) : null}
    </div>
  )
}
