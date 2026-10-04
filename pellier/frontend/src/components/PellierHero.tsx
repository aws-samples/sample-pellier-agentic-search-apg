import { apiFetch } from '../services/apiBase'
/**
 * PellierHero: the storefront's first viewport, direction A.
 *
 * The statement, then the large bar: agentic search, "Search or ask
 * Pellier". Enter opens the docked panel with the question. Under the bar
 * sits one row of suggestions at a time: the store's moments while signed
 * out, and only the signed-in shopper's lab prompts, read from Aurora, once
 * a shopper is chosen. Signed out, the shopper chooser follows. The
 * collection follows directly beneath.
 */
import { useCallback, useEffect, useState } from 'react'
import { ArrowUp } from 'lucide-react'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'
import { splitHeadlineAtAccent } from '../utils/headlineAccent'
import { ASK_BAR, HERO_STATEMENT } from '../copy'
import PersonaConcierge from './PersonaConcierge'
import { useSpotlightSeen } from './PellierSpotlight'

interface LiveScenario {
  id: number
  ordinal: number
  prompt: string
  journeyRole?: 'required' | 'explore'
}

type StatementId = 'fresh' | 'marco' | 'anna' | 'theo' | 'jessica'

/** The lede under each persona's statement. Aurora owns the scenarios below. */
const PERSONA_LEDES: Record<StatementId, string> = {
  fresh: 'Choose who is shopping, then browse a floor arranged around them.',
  marco: 'Travel-ready linen, leather, and natural fibers for a considered edit.',
  anna: 'Thoughtful gifts and warm home objects, considered within your budget.',
  theo: 'Quiet craft, ceramics, and lasting pieces for a slower home rhythm.',
  jessica: 'Throws, towels and soft light for slow evenings at home.',
}

function statementIdFor(personaId: string): StatementId {
  return (personaId in HERO_STATEMENT ? personaId : 'fresh') as StatementId
}

export default function PellierHero() {
  const spotlightSeen = useSpotlightSeen()
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const [searchValue, setSearchValue] = useState('')
  const [suggestions, setSuggestions] = useState<LiveScenario[]>([])
  const personaId = persona?.id ?? 'fresh'
  const statementId = statementIdFor(personaId)
  const statement = HERO_STATEMENT[statementId]
  const headline = splitHeadlineAtAccent(statement.HEADLINE, statement.ACCENT)

  useEffect(() => {
    if (!persona) {
      setSuggestions([])
      return
    }
    let active = true
    const controller = new AbortController()
    setSuggestions([])
    void apiFetch(`/api/scenarios?persona=${encodeURIComponent(persona.id)}`, {
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

  const submitQuery = useCallback(
    (query: string) => {
      const trimmed = query.trim()
      if (!trimmed) return
      openDrawerWithQuery(trimmed)
      setSearchValue('')
    },
    [openDrawerWithQuery],
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
            {PERSONA_LEDES[statementId]}
          </p>
        </div>

        <form role="search" onSubmit={handleSubmit} className="pellier-askbar">
          <div className="pellier-askfield">
            <input
              type="text"
              data-testid="pellier-hero-search"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder={ASK_BAR.PLACEHOLDER}
              aria-label={ASK_BAR.LABEL}
              autoComplete="off"
            />
            <button type="submit" className="pellier-send" aria-label={ASK_BAR.SEND}>
              <ArrowUp size={16} strokeWidth={2.2} aria-hidden="true" />
            </button>
          </div>
          {/* One row of suggestions at a time: the shopper's own prompts once
              one is signed in, the store's moments before. */}
          {persona ? (
            suggestions.length > 0 ? (
              <div
                className="pellier-chips"
                data-testid="pellier-hero-pills"
                role="group"
                aria-label={ASK_BAR.promptsFor(persona.display_name)}
              >
                <span className="pellier-chip-label" aria-hidden="true">{ASK_BAR.TRY}</span>
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
            ) : null
          ) : (
            <div className="pellier-chips" data-testid="pellier-hero-moments" role="group" aria-label="Moments">
              <span className="pellier-chip-label" aria-hidden="true">{ASK_BAR.TRY}</span>
              {ASK_BAR.MOMENTS.map((moment) => (
                <button
                  key={moment}
                  type="button"
                  className="pellier-chip"
                  onClick={() => submitQuery(moment)}
                >
                  {moment}
                </button>
              ))}
            </div>
          )}
        </form>

        {!persona && spotlightSeen ? <PersonaConcierge /> : null}
      </div>
    </section>
  )
}
