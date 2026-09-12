/**
 * PellierHero - the storefront's editorial first viewport.
 *
 * Two connected zones: the shopper request and the editorial photograph.
 *
 * The existing type scale, scenario choice, and drawer contract are retained.
 * Suggestions come from the current persona's live scenarios; submitted
 * requests continue in the same Ask Pellier drawer.
 *
 * The interaction layer is unchanged from the framed version: choose a
 * workshop profile, then submit a query once a profile is active. A query
 * still needs a profile because the floor is ranked per persona, so the
 * search affordance appears with the profile rather than before it.
 */
import { useCallback, useEffect, useState } from 'react'
import { Send, Sparkles } from 'lucide-react'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { asset } from '../utils/assetPath'
import { splitHeadlineAtAccent } from '../utils/headlineAccent'
import { HERO_STATEMENT } from '../copy'
import PersonaConcierge from './PersonaConcierge'
import { useSpotlightSeen } from './PellierSpotlight'
import ResponsiveImage from './ResponsiveImage'

interface LiveScenario {
  id: number
  ordinal: number
  prompt: string
  journeyRole?: 'required' | 'explore'
}

type StatementId = 'fresh' | 'marco' | 'anna' | 'theo'

/**
 * Storefront art direction is fixed by persona. This keeps the first viewport
 * available even when the live database is unavailable; Aurora still owns the
 * selectable shopper records and the guided scenarios below.
 */
const PERSONA_HEROES: Record<
  StatementId,
  { image: string; alt: string; subheadline: string; captionLabel: string; caption: string }
> = {
  fresh: {
    image: '/products/landing-hero-weekender.webp',
    alt: 'Leather weekender on a travertine bench beside linen and an olive branch',
    subheadline:
      'Choose who is shopping, then browse a floor arranged around them.',
    captionLabel: 'The weekend edit',
    caption: 'Take the long way.',
  },
  marco: {
    image: '/products/hero-marco.png',
    alt: 'Leather weekender with folded linen and brass travel details in warm daylight',
    subheadline:
      'Travel-ready linen, leather, and natural fibers for a considered edit.',
    captionLabel: 'The weekend edit',
    caption: 'Take the long way.',
  },
  anna: {
    image: '/products/hero-anna.png',
    alt: 'Ribbon-wrapped gift beside an amber candle, ceramic bud vase, and blank card',
    subheadline:
      'Thoughtful gifts and warm home objects, considered within your budget.',
    captionLabel: 'The gifting edit',
    caption: 'A little thought goes a long way.',
  },
  theo: {
    image: '/products/hero-theo.png',
    alt: 'Charcoal stoneware bowl beside natural linen, a beeswax candle, and olive branches',
    subheadline:
      'Quiet craft, ceramics, and lasting pieces for a slower home rhythm.',
    captionLabel: 'The everyday ritual',
    caption: 'Make room for a slower moment.',
  },
}

function statementFor(personaId: string) {
  const key = (personaId in HERO_STATEMENT ? personaId : 'fresh') as StatementId
  return HERO_STATEMENT[key]
}

interface PellierHeroProps {
  /**
   * Browse the catalog. Defaults to scrolling the `#shop` band, which is
   * what PellierPage does for every other catalog entry point.
   */
  onBrowseCollection?: () => void
}

export default function PellierHero({
  onBrowseCollection,
}: PellierHeroProps) {
  const spotlightSeen = useSpotlightSeen()
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const [searchValue, setSearchValue] = useState('')
  const [suggestions, setSuggestions] = useState<LiveScenario[]>([])
  const personaId = persona?.id ?? 'fresh'
  const hero = PERSONA_HEROES[
    personaId in PERSONA_HEROES ? personaId as StatementId : 'fresh'
  ]
  const statement = statementFor(personaId)
  const headline = splitHeadlineAtAccent(statement.HEADLINE, statement.ACCENT)

  useEffect(() => {
    if (!persona) {
      setSuggestions([])
      return
    }
    let active = true
    const controller = new AbortController()
    setSuggestions([])
    void fetch(`/api/observatory/scenarios?persona=${encodeURIComponent(persona.id)}`, {
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) throw new Error(`Live scenario request failed: ${response.status}`)
        return response.json() as Promise<{ scenarios?: LiveScenario[] }>
      })
      .then(payload => {
        if (active) {
          setSuggestions(
            (payload.scenarios ?? [])
              .filter((scenario) =>
                scenario.journeyRole
                  ? scenario.journeyRole === 'required'
                  : scenario.ordinal <= 3,
              )
              .slice(0, 3),
          )
        }
      })
      .catch(() => {
        if (active) setSuggestions([])
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [persona])

  const browseCollection = useCallback(() => {
    if (onBrowseCollection) {
      onBrowseCollection()
      return
    }
    document.getElementById('shop')?.scrollIntoView({ behavior: 'smooth' })
  }, [onBrowseCollection])

  const submitQuery = useCallback(
    (query: string) => {
      if (!persona) return
      const trimmed = query.trim()
      if (!trimmed) return
      openDrawerWithQuery(trimmed)
      setSearchValue('')
    },
    [openDrawerWithQuery, persona],
  )

  const handleSubmit = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault()
      submitQuery(searchValue)
    },
    [searchValue, submitQuery],
  )

  return (
    <section
      data-testid="pellier-hero"
      data-persona={personaId}
      aria-label="Pellier collection"
      className="pellier-hero"
    >
      <div className="pellier-hero-inner">
        <div className="pellier-hero-copy">
          <span className="pellier-eyebrow">Pellier</span>

          <h1
            data-testid="pellier-hero-headline"
            className="pellier-statement"
          >
            {headline.before}
            {headline.accent ? <em>{headline.accent}</em> : null}
            {headline.after}
          </h1>

          <p
            data-testid="pellier-hero-subheadline"
            className="pellier-hero-lede"
          >
            {hero.subheadline}
          </p>

          {persona ? (
            /* Width is the copy column, not a fixed max: a wider block spilled
               the suggestion pills over the photograph and clipped one
               mid-word. */
            <div className="w-full">
              <form
                role="search"
                onSubmit={handleSubmit}
                className="relative w-full"
              >
                <Sparkles
                  aria-hidden="true"
                  className="absolute left-5 top-1/2 z-10 -translate-y-1/2 text-accent"
                  size={19}
                />
                <input
                  type="text"
                  data-testid="pellier-hero-search"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  placeholder={
                    'Ask Pellier anything...'
                  }
                  aria-label="Ask Pellier anything"
                  className="
                    h-[56px] w-full rounded-full border border-[rgba(24,26,31,0.16)]
                    bg-[rgba(255,255,255,0.94)] pl-[52px] pr-[58px]
                    font-sans text-[15px] text-espresso shadow-warm-sm
                    outline-none transition
                    placeholder:text-[rgba(24,26,31,0.48)]
                    focus:border-[rgba(24,26,31,0.34)] focus:ring-2
                    focus:ring-[rgba(154,52,18,0.18)]
                  "
                />
                {searchValue.trim() ? (
                  <button
                    type="submit"
                    aria-label="Send"
                    className="
                      absolute right-[5px] top-1/2 flex h-[46px] w-[46px]
                      -translate-y-1/2 items-center justify-center rounded-full
                      bg-espresso text-cream transition hover:bg-accent
                      focus-visible:outline-none focus-visible:ring-2
                      focus-visible:ring-espresso focus-visible:ring-offset-2
                    "
                  >
                    <Send size={18} />
                  </button>
                ) : null}
              </form>

              {suggestions.length > 0 ? (
                <div className="pellier-hero-suggestions">
                  <p className="pellier-hero-suggestions-label">A place to start for {persona.display_name}</p>
                  <div
                    data-testid="pellier-hero-pills"
                    className="pellier-hero-pills"
                    role="group"
                    aria-label="Suggested queries"
                  >
                    {suggestions.map(scenario => (
                      <button
                        key={scenario.id}
                        type="button"
                        onClick={() => submitQuery(scenario.prompt)}
                        className="pellier-prompt-pill"
                      >
                        {scenario.prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* Browsing stays available with a profile active, but as the
                  quiet action: asking is the primary one here. */}
              <button
                type="button"
                className="pellier-action-quiet mt-1"
                onClick={browseCollection}
              >
                {HERO_STATEMENT.CTA}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="pellier-action"
              data-testid="pellier-hero-cta"
              onClick={browseCollection}
            >
              {HERO_STATEMENT.CTA}
            </button>
          )}
          {spotlightSeen ? <PersonaConcierge /> : null}
        </div>

        <figure className="pellier-hero-media">
          {personaId === 'fresh' ? (
            <ResponsiveImage
              src={hero.image}
              alt={hero.alt}
              widths={[480, 960, 1600]}
              sizes="(min-width: 900px) 55vw, 100vw"
              loading="eager"
              pictureClassName="block h-full w-full"
            />
          ) : (
            <img
              data-testid="persona-hero-image"
              src={asset(hero.image)}
              alt={hero.alt}
              width={1672}
              height={941}
              loading="eager"
              decoding="async"
            />
          )}
          <figcaption className="pellier-hero-caption">
            <span>{hero.captionLabel}</span>
            <p>{hero.caption}</p>
          </figcaption>
        </figure>

      </div>
    </section>
  )
}
