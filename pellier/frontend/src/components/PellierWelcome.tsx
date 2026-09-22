import { apiFetch } from '../services/apiBase'
/**
 * Live concierge empty state.
 *
 * Existing editorial photography frames the live catalog and suggested turns.
 * A failed data-plane read remains visible; the photograph is never a claim
 * about product availability or a substitute recommendation.
 */
import { useEffect, useState } from 'react'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { PellierProduct } from '../services/types'
import { imageSrc } from '../utils/assetPath'
import { welcomeScene } from '../data/welcomeScenes'
import '../styles/pellier-welcome.css'

interface PellierWelcomeProps {
  onSend: (text: string) => void
  persona?: PersonaSnapshot | null
}

interface LiveScenario {
  id: number
  ordinal?: number
  prompt: string
  journeyRole?: 'required' | 'explore'
}

type TimeOfDay = 'morning' | 'afternoon' | 'evening'

function timeOfDay(): TimeOfDay {
  const hour = new Date().getHours()
  if (hour < 12) return 'morning'
  if (hour < 17) return 'afternoon'
  return 'evening'
}

const TIME_GREETING: Record<TimeOfDay, string> = {
  morning: 'Good morning',
  afternoon: 'Good afternoon',
  evening: 'Good evening',
}

const TIME_EYEBROW: Record<TimeOfDay, string> = {
  morning: 'This morning at Pellier',
  afternoon: 'This afternoon at Pellier',
  evening: 'Tonight at Pellier',
}

export function composeWelcomeGreeting(
  timeGreeting: string,
  greetingSuffix: string,
): string {
  const suffix = greetingSuffix.trim()
  return `${timeGreeting}${suffix}${suffix.endsWith('.') ? '' : '.'}`
}

export default function PellierWelcome({ onSend, persona }: PellierWelcomeProps) {
  const [catalog, setCatalog] = useState<PellierProduct[]>([])
  const [scenarios, setScenarios] = useState<LiveScenario[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const [imageFailed, setImageFailed] = useState(false)
  const profileId = persona?.id ?? 'fresh'
  const tod = timeOfDay()

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setCatalog([])
    setScenarios([])
    setError(null)
    setLoading(true)
    setImageFailed(false)
    const timeout = window.setTimeout(() => controller.abort(new Error('Edit request timed out')), 20000)

    void Promise.all([
      apiFetch(`/api/products?persona=${encodeURIComponent(profileId)}`, {
        credentials: 'include',
        signal: controller.signal,
      }),
      apiFetch(`/api/observatory/scenarios?persona=${encodeURIComponent(profileId)}`, {
        signal: controller.signal,
      }),
    ])
      .then(async ([catalogResponse, scenarioResponse]) => {
        if (!catalogResponse.ok || !scenarioResponse.ok) {
          throw new Error('Your edit is taking a little longer to arrive. Please try again, or ask Pellier below.')
        }
        return Promise.all([
          catalogResponse.json() as Promise<PellierProduct[]>,
          scenarioResponse.json() as Promise<{ scenarios?: LiveScenario[] }>,
        ])
      })
      .then(([products, payload]) => {
        if (!active) return
        setCatalog(products)
        setScenarios(payload.scenarios ?? [])
        setLoading(false)
      })
      .catch(() => {
        if (!active) return
        setError('Your edit is taking a little longer to arrive. Please try again, or ask Pellier below.')
        setLoading(false)
      })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      window.clearTimeout(timeout)
      active = false
      controller.abort()
    }
  }, [profileId, revision])

  const scene = welcomeScene(profileId)
  const greeting = composeWelcomeGreeting(
    TIME_GREETING[tod],
    persona && persona.id !== 'fresh' ? `, ${persona.display_name.split(' ')[0]}` : '',
  )
  const primary = scenarios.filter((scenario, index) =>
    scenario.journeyRole
      ? scenario.journeyRole === 'required'
      : (scenario.ordinal ?? index + 1) <= 3,
  )
  const more = scenarios.filter((scenario, index) =>
    scenario.journeyRole
      ? scenario.journeyRole === 'explore'
      : (scenario.ordinal ?? index + 1) > 3,
  )

  return (
    <div className="sf-welcome">
      {!imageFailed && (
        <div className="sf-cover">
          <img src={imageSrc(scene.image)} alt={scene.alt} className="sf-cover-img"
            width={1672} height={941} decoding="async" onError={() => setImageFailed(true)} />
          <div className="sf-cover-overlay">
            <div className="sf-cover-eyebrow">{scene.label}</div>
          </div>
        </div>
      )}

      <div className="sf-body">
        <div className="sf-eyebrow-row">
          <span className="sf-eyebrow-sm">{TIME_EYEBROW[tod]}</span>
          <span className="sf-eyebrow-rule" />
        </div>

        <h2 className="sf-greeting"><em>{greeting}</em></h2>
        <p className="sf-context">
          {error
            ? error
            : catalog.length
              ? `${catalog.length} pieces in your current edit. Tell me what you have in mind.`
              : loading ? 'Opening your edit and a few ideas to get started…' : 'Tell me what you have in mind. We can find a place to start.'}
        </p>
        {error ? <button type="button" className="pellier-retry" onClick={() => setRevision(value => value + 1)}>Try again</button> : null}

        {!error && primary.length > 0 ? (
          <section
            className="sf-section"
            aria-label="Ideas to begin your conversation"
          >
            <div className="sf-section-head">
              <span className="sf-eyebrow-sm sf-eyebrow-red">
                <span className="sf-dot" />
                A few ideas to begin
              </span>
            </div>
            <div className="sf-actions-stack">
              {primary.map((scenario, index) => (
                <button
                  key={scenario.id}
                  type="button"
                  className={`sf-action ${index === 0 ? 'sf-action-primary' : ''}`}
                  onClick={() => onSend(scenario.prompt)}
                >
                  {scenario.prompt}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {more.length > 0 ? (
          <>
            <div className="sf-divider" />
            <p className="sf-prompt">Something else in mind?</p>
            <section
              className="sf-postscript-list"
              aria-label="Explore further"
            >
              {more.map((scenario) => (
                <button
                  key={scenario.id}
                  type="button"
                  className="sf-overheard"
                  onClick={() => onSend(scenario.prompt)}
                >
                  <span className="sf-overheard-line">
                    <span className="sf-overheard-bullet">&middot;</span>
                    <span className="sf-overheard-quote">&ldquo;{scenario.prompt}&rdquo;</span>
                  </span>
                </button>
              ))}
            </section>
          </>
        ) : null}
      </div>
    </div>
  )
}
