/**
 * PersonaConcierge - the hero's profile surface.
 *
 * Wraps the persona selection that used to sit inline in PellierHero. The
 * behaviour is unchanged: selecting a profile calls `switchPersona`, which
 * mints a new session and reranks the floor. Nothing here invents
 * personalization the application does not already perform.
 *
 * The concierge requires one of the three workshop profiles. The action only
 * opens once a profile is active, so the UI cannot bypass the personalization
 * contract with a contradictory guest path.
 */
import { useEffect, useState } from 'react'
import { usePersona, type PersonaListItem } from '../contexts/PersonaContext'
import { getPersonaPortrait } from '../data/personaPhotos'
import { HERO_CONCIERGE } from '../copy'

export default function PersonaConcierge() {
  const { persona, switchPersona, switching, switchError } = usePersona()
  const [profiles, setProfiles] = useState<PersonaListItem[]>([])
  const [retryVersion, setRetryVersion] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (persona) return
    let active = true
    setError(null)
    setLoading(true)
    void fetch('/api/observatory/personas')
      .then(async (response) => {
        if (!response.ok) throw new Error('We couldn’t load the profiles. Please try again.')
        return response.json() as Promise<PersonaListItem[]>
      })
      .then((items) => { if (active) setProfiles(items.filter((item) => item.id !== 'fresh')) })
      .catch(() => { if (active) setError('We couldn’t load the profiles. Please try again.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [persona, retryVersion])

  const selectProfile = async (profileId: string) => {
    await switchPersona(profileId)
  }

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
      <ul className="pellier-concierge-profiles" aria-busy={loading || switching}>
        {profiles.map((profile) => {
          const portrait = getPersonaPortrait(profile.id)
          return (
            <li key={profile.id}>
              <button
                type="button"
                className="pellier-profile"
                data-testid={`hero-profile-${profile.id}`}
                aria-pressed={false}
                disabled={switching}
                onClick={() => void selectProfile(profile.id)}
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
                  {profile.role_tag}
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

      {/* Stated at the point of choice, not deferred to a lab page: a
          participant who reads this selector as an identity assertion will
          misread every later policy decision. */}
      <p
        data-testid="persona-identity-boundary"
        className="pellier-concierge-identity-note"
      >
        {HERO_CONCIERGE.IDENTITY_BOUNDARY}
      </p>
    </aside>
  )
}
