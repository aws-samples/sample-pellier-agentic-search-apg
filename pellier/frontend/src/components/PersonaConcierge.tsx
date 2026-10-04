import { apiFetch } from '../services/apiBase'
/**
 * PersonaConcierge - the home page's shopper chooser.
 *
 * Shows the four customers: Marco, Anna, Theo and Jessica. Choosing one signs
 * in with that shopper's demo account and opens their edit
 * (`useShopperSignIn`). Browsing without choosing stays signed out, which is
 * the neutral new-visitor store. Staff never appear here: the list keeps only
 * the four demo shoppers, whatever the profile read returns.
 */
import { useEffect, useState } from 'react'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import { getPersonaPortrait } from '../data/personaPhotos'
import { chooserShoppers, isWorkshopShopper, useShopperSignIn } from '../hooks/useShopperSignIn'
import { HERO_CONCIERGE } from '../copy'

export default function PersonaConcierge() {
  const { persona, switchError } = usePersona()
  const { choose, busy, error: signInError } = useShopperSignIn()
  const [profiles, setProfiles] = useState<PersonaListItem[]>([])
  const [retryVersion, setRetryVersion] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (persona) return
    let active = true
    setError(null)
    setLoading(true)
    void apiFetch('/api/personas')
      .then(async (response) => {
        if (!response.ok) throw new Error('We couldn’t load the profiles. Please try again.')
        return response.json() as Promise<PersonaListItem[]>
      })
      .then((items) => { if (active) setProfiles(chooserShoppers(items)) })
      .catch(() => { if (active) setError('We couldn’t load the profiles. Please try again.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [persona, retryVersion])

  if (persona) return null

  return (
    <aside
      className="pellier-concierge"
      data-testid="persona-concierge"
      aria-labelledby="persona-concierge-title"
    >
      <div className="pellier-concierge-heading">
        <span className="pellier-eyebrow">{HERO_CONCIERGE.EYEBROW}</span>
        <h2 id="persona-concierge-title">{HERO_CONCIERGE.TITLE}</h2>
        <p>{HERO_CONCIERGE.HELPER}</p>
      </div>

      {loading ? <p className="pellier-profile-loading" role="status">Finding your profiles…</p> : null}
      <ul className="pellier-concierge-profiles" aria-busy={loading || Boolean(busy)}>
        {profiles.map((profile) => {
          const portrait = getPersonaPortrait(profile.id)
          return (
            <li key={profile.id}>
              <button
                type="button"
                className="pellier-profile"
                data-testid={`hero-profile-${profile.id}`}
                aria-pressed={false}
                aria-busy={busy === profile.id || undefined}
                disabled={Boolean(busy)}
                onClick={() => { if (isWorkshopShopper(profile.id)) void choose(profile.id) }}
              >
                <span
                  className="pellier-profile-portrait"
                  style={
                    portrait ? undefined : { background: profile.avatar_color }
                  }
                >
                  {portrait ? (
                    <img
                      src={portrait}
                      alt=""
                      aria-hidden="true"
                      loading="lazy"
                      decoding="async"
                      width={160}
                      height={160}
                    />
                  ) : null}
                </span>
                <span className="pellier-profile-name">
                  {profile.display_name}
                </span>
                <span className="pellier-profile-note">
                  {busy === profile.id ? HERO_CONCIERGE.SIGNING_IN : profile.role_tag}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {error || switchError ? (
        <div className="pellier-recovery" role="alert">
          <p>{error ?? switchError}</p>
          {error ? <button type="button" className="pellier-retry" onClick={() => setRetryVersion(v => v + 1)}>Try again</button> : null}
        </div>
      ) : null}
      {signInError ? (
        <div className="pellier-recovery" role="alert" data-testid="persona-sign-in-error">
          <p>{HERO_CONCIERGE.FAILED} <code>{signInError}</code></p>
        </div>
      ) : null}

      {/* Stated at the point of choice, not deferred to a lab page: the
          choice is a sign-in, and the signed token is what Pellier trusts. */}
      <p
        data-testid="persona-identity-boundary"
        className="pellier-concierge-identity-note"
      >
        {HERO_CONCIERGE.IDENTITY_BOUNDARY}
      </p>
    </aside>
  )
}
