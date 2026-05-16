/**
 * BoutiqueHero — editorial photograph with center-aligned typography.
 *
 * Full-bleed photograph background (Olive Branch Vessel). Typography
 * overlays the right portion of the photograph where the cream wall
 * provides a clean reading surface. Within the typography column,
 * every element center-aligns for symmetric editorial breathing room.
 *
 * Search bar: substantial pill (~58px tall), Sparkles icon left,
 * espresso-filled circular mic button right — signals AI-powered search.
 *
 * Mobile (<768px): typography column fills full width, gradient overlay
 * ensures readability against the photograph's underlying composition.
 */
import { useCallback, useState } from 'react'
import { Sparkles, Mic, Send, MicOff } from 'lucide-react'
import { useUI } from '../contexts/UIContext'
import { usePersona } from '../contexts/PersonaContext'
import {
  heroPillsForPersona,
  becauseChipsForPersona,
  MARCO_BUILDER_SESSION_QUERY,
  type BecauseChip,
} from '../data/personaCurations'
import { useFloorCheckWorkshopCue } from '../hooks/useFloorCheckWorkshopCue'
import { useVoiceSearch } from '../hooks/useVoiceSearch'
import { PresencePill } from '../shared'
import { asset } from '../utils/assetPath'
import { splitHeadlineAtRe } from '../utils/headlineAccent'

// Per-persona hero images (landscape, in public/products/).
// Falls back to the fresh hero for unknown personas.
const PERSONA_HERO_IMAGES: Record<string, string> = {
  fresh: asset('/products/hero-fresh-2.png'),
  marco: asset('/products/hero-marco.png'),
  anna: asset('/products/hero-anna.png'),
  theo: asset('/products/hero-theo.png'),
}

// Trust strip restyled as Agent Capabilities \u2014 bold lead reads as the
// agent's skill, the trailing fragment keeps the shipping/returns
// boilerplate on the page without leading with it. The first three
// items map to the agent surfaces inside /atelier (memory, tools,
// grounding) so a re:Invent attendee sees the same vocabulary on both
// sides of the demo.
interface CapabilityItem {
  /** Bold lead clause \u2014 agent capability. */
  lead: string
  /** Optional trailing clause \u2014 operational reassurance. */
  trail?: string
}
const TRUST_ITEMS: CapabilityItem[] = [
  { lead: 'Reads live inventory' },
  { lead: 'Remembers your taste' },
  { lead: 'Cites every source' },
  { lead: 'Hands off to a human stylist' },
  { lead: 'Ships in 1\u20132 days', trail: 'Free over $150' },
]

// Visual treatment per because-chip kind. Same dashed-italic shell, just
// a different eyebrow label color so the categories are scannable.
const BECAUSE_KIND_LABEL: Record<BecauseChip['kind'], string> = {
  memory: 'memory',
  trend: 'trend',
  inventory: 'inventory',
  weather: 'weather',
}

export default function BoutiqueHero() {
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const { showBuilderSessionGap } = useFloorCheckWorkshopCue()
  const suggestions = heroPillsForPersona(persona?.id)
  const becauseChips = becauseChipsForPersona(persona?.id)
  const heroImage = PERSONA_HERO_IMAGES[persona?.id ?? 'fresh'] ?? PERSONA_HERO_IMAGES.fresh
  const [searchValue, setSearchValue] = useState('')

  // Amazon Transcribe voice search — interim transcripts fill the
  // search bar, final transcript auto-fires the query.
  const { isListening, startListening, stopListening } = useVoiceSearch({
    onInterimTranscript: (text) => setSearchValue(text),
    onFinalTranscript: (text) => {
      setSearchValue('')
      openDrawerWithQuery(text)
    },
  })

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = searchValue.trim()
      if (!trimmed) return
      openDrawerWithQuery(trimmed)
      setSearchValue('')
    },
    [searchValue, openDrawerWithQuery],
  )

  const handlePillClick = useCallback(
    (query: string) => {
      openDrawerWithQuery(query)
    },
    [openDrawerWithQuery],
  )

  const heroHeadline = splitHeadlineAtRe('Search, re:Engineered.')

  /** Marco + exercise: align "Builder's Session" over Turn 4 pill on wide viewports. */
  const marcoBuilderSessionBand =
    persona?.id === 'marco' &&
    showBuilderSessionGap &&
    suggestions[3] === MARCO_BUILDER_SESSION_QUERY

  return (
    <>
    <section data-testid="boutique-hero" aria-label="Search and discover" className="relative h-[78vh] min-h-[720px]">
      {/* ── Editorial photo + wash — clipped so tall images never spill beyond
           the viewport. Foreground avoids overflow:hidden so Marco pill rails
           are not clipped at the viewport edge. ── */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        <img
          src={heroImage}
          alt="Editorial boutique hero"
          className="absolute inset-0 h-full w-full object-cover object-[20%_center]"
        />
        <div
          className="absolute inset-0 bg-gradient-to-r from-transparent via-[#f7f0e6]/20 to-[#f7f0e6]/45"
          aria-hidden="true"
        />
      </div>

      {/* ── Typography overlay — centered content ── */}
      <div className="relative z-10 mx-auto flex h-full max-w-7xl items-center justify-center px-8">
          <div
            className="min-w-0 w-full max-w-4xl py-12 md:py-0
                       flex flex-col items-center text-center"
          >
            {/* Presence — discreet concierge cue (breathing dot + label).
                Shared atom with Atelier TopBar; session tail only when a
                persona is signed in. */}
            <div data-testid="boutique-hero-presence" className="mb-5">
              <PresencePill surface="boutique" personaId={persona?.id} />
            </div>

            {/* Eyebrow — "• SUMMER EDIT • NO. 06 •" — matches
                WeekendEditorial eyebrow type treatment exactly, with
                burgundy dot separators. */}
            <div
              data-testid="boutique-hero-eyebrow"
              className="flex items-center gap-3 mb-5 text-[13px] font-sans font-semibold tracking-[0.22em] uppercase text-espresso"
            >
              <span aria-hidden="true" className="text-accent" style={{ fontSize: '9px' }}>&#9679;</span>
              <span>Summer Edit</span>
              <span aria-hidden="true" className="text-accent" style={{ fontSize: '5px' }}>&#9679;</span>
              <span>No. 06</span>
              <span aria-hidden="true" className="text-accent" style={{ fontSize: '9px' }}>&#9679;</span>
            </div>

            {/* Headline — same Fraunces italic treatment as
                WeekendEditorial, but sized up for hero prominence. */}
            <h1
              data-testid="boutique-hero-headline"
              className="whitespace-nowrap font-display italic"
              style={{
                fontSize: 'clamp(44px, 6vw, 76px)',
                lineHeight: 1.05,
                letterSpacing: '-0.015em',
                fontWeight: 400,
              }}
            >
              {heroHeadline.tail ? (
                <>
                  <span className="text-espresso">{heroHeadline.lead}</span>
                  <span className="text-accent-ink">{heroHeadline.tail}</span>
                </>
              ) : (
                <span className="text-espresso">{heroHeadline.lead}</span>
              )}
            </h1>

            {/* Subheadline — same Instrument Sans / ink-soft treatment as
                WeekendEditorial subhead, sized up for hero prominence. */}
            <p
              data-testid="boutique-hero-subheadline"
              className="mx-auto mt-6 max-w-[600px] font-sans text-ink-soft"
              style={{
                fontSize: 'clamp(17px, 1.4vw, 21px)',
                lineHeight: 1.55,
              }}
            >
              Tell Pellier what you&rsquo;re looking for.
              <br />
              Watch the pieces find you.
            </p>

            {/* Search input — substantial pill, sparkles left, espresso mic right */}
            <form
              onSubmit={handleSubmit}
              className="mt-8 md:mt-10 w-full"
              role="search"
              style={{ maxWidth: '640px' }}
            >
              <div className="relative">
                {/* Sparkles icon — left. Burgundy for clear visibility
                    against the cream input. z-10 keeps it above the
                    input's own focus ring on click. */}
                <span
                  className="absolute left-6 top-1/2 -translate-y-1/2 pointer-events-none z-10 text-accent"
                  aria-hidden="true"
                >
                  <Sparkles size={22} strokeWidth={2} />
                </span>

                <input
                  type="text"
                  data-testid="boutique-hero-search"
                  value={searchValue}
                  onChange={(e) => setSearchValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      const trimmed = searchValue.trim()
                      if (!trimmed) return
                      openDrawerWithQuery(trimmed)
                      setSearchValue('')
                    }
                  }}
                  placeholder={isListening ? 'Listening...' : 'Ask Pellier anything...'}
                  aria-label="Ask Pellier anything"
                  className="
                    w-full rounded-full
                    bg-[rgba(255,250,240,0.96)] backdrop-blur-md
                    border border-[rgba(31,20,16,0.12)]
                    pl-[60px] pr-[64px]
                    font-sans
                    placeholder:text-[rgba(31,20,16,0.42)]
                    focus:bg-[rgba(255,250,240,0.98)] focus:border-[rgba(31,20,16,0.18)]
                    focus:ring-2 focus:ring-[rgba(31,20,16,0.06)]
                    focus:outline-none
                    transition-all duration-fade ease-out
                  "
                  style={{
                    height: '66px',
                    fontSize: '17px',
                    color: '#1f1410',
                    fontFamily: 'var(--sans)',
                    boxShadow:
                      '0 2px 12px rgba(31, 20, 16, 0.06), 0 1px 3px rgba(31, 20, 16, 0.04)',
                  }}
                />

                {/* Right button: Send when typing, Mic when empty, MicOff when listening */}
                <button
                  type={searchValue.trim() ? 'submit' : 'button'}
                  onClick={
                    searchValue.trim()
                      ? undefined // form submit handles it
                      : isListening
                        ? stopListening
                        : startListening
                  }
                  aria-label={
                    searchValue.trim()
                      ? 'Send'
                      : isListening
                        ? 'Stop listening'
                        : 'Voice search'
                  }
                  className="
                    absolute right-[7px] top-1/2 -translate-y-1/2
                    flex items-center justify-center rounded-full
                    transition-all duration-fade ease-out
                    hover:scale-105
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(31,20,16,0.3)]
                  "
                  style={{
                    width: '50px',
                    height: '50px',
                    background: isListening ? 'var(--accent)' : '#1f1410',
                    color: 'var(--cream-warm)',
                    cursor: 'pointer',
                    // Pulsing ring when listening
                    boxShadow: isListening
                      ? '0 0 0 4px rgba(154, 52, 18, 0.3), 0 0 0 8px rgba(154, 52, 18, 0.15)'
                      : 'none',
                    animation: isListening ? 'pulse 1.5s ease-in-out infinite' : 'none',
                  }}
                >
                  {searchValue.trim() ? (
                    <Send size={20} strokeWidth={2} />
                  ) : isListening ? (
                    <MicOff size={20} strokeWidth={1.75} />
                  ) : (
                    <Mic size={20} strokeWidth={1.75} />
                  )}
                </button>
              </div>
            </form>

            {/* Marco + exercise (lg): labels absolutely positioned on the same
                baseline — Try asking centered in the gap between pills 2 & 3,
                Builder's Session centered over pill 4 (track scales with %). */}
            <div className="mt-0 w-full min-w-0">
              {marcoBuilderSessionBand ? (
                <>
                  {/* lg: Fluid 5-column track (max 965px). Fixed 185px columns
                     exceeded max-w-4xl and clipped pill 5; labels use the same
                     gap math off the fluid track width. */}
                  <div
                    className="mx-auto mt-6 hidden w-full min-w-0 pb-1 md:mt-8 lg:block"
                    data-testid="boutique-hero-marco-pill-band"
                  >
                    <div
                      className="mx-auto flex w-full max-w-[965px] flex-col"
                      style={{
                        fontFamily: 'var(--sans)',
                        color: '#1f1410',
                      }}
                    >
                      <div
                        data-testid="boutique-hero-try-asking"
                        className="relative w-full shrink-0"
                        style={{
                          height: '24px',
                          marginBottom: '4px',
                        }}
                      >
                        <span
                          style={{
                            position: 'absolute',
                            left: 'calc((100% - 40px) * 2 / 5 + 15px)',
                            bottom: 0,
                            transform: 'translateX(-50%)',
                            fontSize: '16px',
                            fontWeight: 500,
                            lineHeight: 1.2,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          Try asking
                        </span>
                        <span
                          data-testid="boutique-hero-builder-session-eyebrow"
                          className="font-semibold uppercase"
                          style={{
                            position: 'absolute',
                            left: 'calc((100% - 40px) * 7 / 10 + 30px)',
                            bottom: 0,
                            transform: 'translateX(-50%)',
                            width:
                              'clamp(116px, calc((100% - 40px) / 5), 185px)',
                            boxSizing: 'border-box',
                            textAlign: 'center',
                            fontSize: '9px',
                            lineHeight: 1.25,
                            color: 'rgba(196, 69, 54, 0.98)',
                            letterSpacing: '0.16em',
                          }}
                        >
                          Builder&apos;s Session · Turn 4
                        </span>
                      </div>

                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(5, minmax(0, 1fr))',
                          columnGap: '10px',
                          rowGap: '12px',
                          width: '100%',
                          maxWidth: '965px',
                          marginInline: 'auto',
                          marginTop: '10px',
                        }}
                      >
                        {suggestions.map((query) => {
                          const isMarcoWarehouseExercise =
                            persona?.id === 'marco' &&
                            showBuilderSessionGap &&
                            query === MARCO_BUILDER_SESSION_QUERY
                          return (
                            <button
                              key={query}
                              type="button"
                              data-testid={
                                isMarcoWarehouseExercise
                                  ? 'boutique-hero-pill-marco-builder-session'
                                  : undefined
                              }
                              aria-describedby={
                                isMarcoWarehouseExercise
                                  ? 'boutique-hero-marco-exercise-hint'
                                  : undefined
                              }
                              onClick={() => handlePillClick(query)}
                              className={[
                                'rounded-[10px] border transition-all duration-fade ease-out cursor-pointer',
                                'hover:border-[rgba(31,20,16,0.32)] hover:bg-[#f5eddf]',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(31,20,16,0.15)]',
                                isMarcoWarehouseExercise
                                  ? 'border-dashed border-[rgba(196,69,54,0.55)] bg-[rgba(250,243,232,0.98)]'
                                  : 'border border-[rgba(31,20,16,0.18)]',
                              ].join(' ')}
                              style={{
                                fontFamily: 'var(--sans)',
                                fontSize: '14px',
                                fontWeight: 400,
                                lineHeight: 1.35,
                                color: '#1f1410',
                                padding: '12px 20px',
                                background: isMarcoWarehouseExercise
                                  ? 'rgba(255, 252, 247, 0.95)'
                                  : 'var(--cream-warm)',
                                width: '100%',
                                minWidth: 0,
                                boxSizing: 'border-box',
                                maxWidth: '185px',
                                marginInline: 'auto',
                                minHeight: '58px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                textAlign: 'center',
                              }}
                            >
                              {query}
                            </button>
                          )
                        })}
                      </div>

                      <p
                        id="boutique-hero-marco-exercise-hint"
                        data-testid="boutique-hero-marco-exercise-hint"
                        className="mt-3 w-full max-w-[965px] px-3 py-2.5 text-center font-sans font-medium leading-snug"
                        style={{
                          alignSelf: 'center',
                          fontSize: '13px',
                          color: '#1a1411',
                          background: 'rgba(248, 240, 228, 0.98)',
                          border: '1px solid rgba(31, 20, 16, 0.18)',
                          borderRadius: '10px',
                          boxShadow: '0 1px 3px rgba(31, 20, 16, 0.08)',
                          boxSizing: 'border-box',
                        }}
                      >
                        Wire{' '}
                        <span className="font-mono text-[12px] font-semibold text-[#1f1410]">
                          floor_check
                        </span>{' '}
                        so Stock Keeper can answer the Turn&nbsp;4 warehouse question from live
                        inventory.
                      </p>
                    </div>
                  </div>

                  <div
                    data-testid="boutique-hero-try-asking-mobile"
                    className="mt-6 flex w-full flex-col items-center gap-1 md:mt-8 lg:hidden"
                    style={{
                      fontFamily: 'var(--sans)',
                      fontSize: '16px',
                      fontWeight: 500,
                      color: '#1f1410',
                    }}
                  >
                    <span>Try asking</span>
                    <span
                      className="font-sans font-semibold uppercase"
                      style={{
                        fontSize: '9px',
                        lineHeight: 1.25,
                        color: 'rgba(196, 69, 54, 0.98)',
                        letterSpacing: '0.16em',
                      }}
                    >
                      Builder&apos;s Session · Turn 4
                    </span>
                  </div>
                  <div
                    data-testid="boutique-hero-pills"
                    className="mt-4 flex flex-wrap justify-center gap-2.5 lg:hidden"
                    role="listbox"
                    aria-label="Suggested queries"
                  >
                    {suggestions.map((query) => {
                      const isMarcoWarehouseExercise =
                        persona?.id === 'marco' &&
                        showBuilderSessionGap &&
                        query === MARCO_BUILDER_SESSION_QUERY
                      return (
                        <button
                          key={query}
                          type="button"
                          data-testid={
                            isMarcoWarehouseExercise
                              ? 'boutique-hero-pill-marco-builder-session'
                              : undefined
                          }
                          aria-describedby={
                            isMarcoWarehouseExercise
                              ? 'boutique-hero-marco-exercise-hint-mobile'
                              : undefined
                          }
                          onClick={() => handlePillClick(query)}
                          className={[
                            'rounded-[10px] border transition-all duration-fade ease-out cursor-pointer',
                            'hover:border-[rgba(31,20,16,0.32)] hover:bg-[#f5eddf]',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(31,20,16,0.15)]',
                            isMarcoWarehouseExercise
                              ? 'border-dashed border-[rgba(196,69,54,0.55)] bg-[rgba(250,243,232,0.98)]'
                              : 'border border-[rgba(31,20,16,0.18)]',
                          ].join(' ')}
                          style={{
                            fontFamily: 'var(--sans)',
                            fontSize: '14px',
                            fontWeight: 400,
                            lineHeight: 1.35,
                            color: '#1f1410',
                            padding: '12px 20px',
                            background: isMarcoWarehouseExercise
                              ? 'rgba(255, 252, 247, 0.95)'
                              : 'var(--cream-warm)',
                            width: '185px',
                            minHeight: '58px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            textAlign: 'center',
                            flex: '0 0 auto',
                          }}
                        >
                          {query}
                        </button>
                      )
                    })}
                  </div>
                  <p
                    id="boutique-hero-marco-exercise-hint-mobile"
                    data-testid="boutique-hero-marco-exercise-hint-mobile"
                    className="mx-auto mt-3 w-full max-w-[640px] px-3 py-2.5 text-center font-sans font-medium leading-snug lg:hidden"
                    style={{
                      fontSize: '13px',
                      color: '#1a1411',
                      background: 'rgba(248, 240, 228, 0.98)',
                      border: '1px solid rgba(31, 20, 16, 0.18)',
                      borderRadius: '10px',
                      boxShadow: '0 1px 3px rgba(31, 20, 16, 0.08)',
                    }}
                  >
                    Wire{' '}
                    <span className="font-mono text-[12px] font-semibold text-[#1f1410]">
                      floor_check
                    </span>{' '}
                    so Stock Keeper can answer the Turn&nbsp;4 warehouse question from live
                    inventory.
                  </p>
                </>
              ) : (
                <>
                  <div
                    data-testid="boutique-hero-try-asking"
                    className="mt-6 flex w-full justify-center md:mt-8"
                    style={{
                      fontFamily: 'var(--sans)',
                      fontSize: '16px',
                      fontWeight: 500,
                      color: '#1f1410',
                    }}
                  >
                    Try asking
                  </div>

                  {(persona?.id === 'anna' || persona?.id === 'theo') && (
                    <p
                      data-testid="boutique-hero-observe-hint"
                      className="mx-auto mt-2 max-w-[640px] text-center font-sans"
                      style={{
                        fontSize: '13px',
                        lineHeight: 1.45,
                        color: 'rgba(31, 20, 16, 0.58)',
                      }}
                    >
                      {persona?.id === 'anna' ? (
                        <>
                          Observe &amp; learn — hybrid + rerank demo.{' '}
                          <strong style={{ color: 'rgba(31, 20, 16, 0.72)', fontWeight: 600 }}>
                            No participant exercise
                          </strong>{' '}
                          on this persona.
                        </>
                      ) : (
                        <>
                          Observe &amp; learn — write path + audit trail demo.{' '}
                          <strong style={{ color: 'rgba(31, 20, 16, 0.72)', fontWeight: 600 }}>
                            No participant exercise
                          </strong>{' '}
                          on this persona.
                        </>
                      )}
                    </p>
                  )}

                  <div
                    data-testid="boutique-hero-pills"
                    className="mt-4 flex flex-wrap justify-center gap-2.5"
                    role="listbox"
                    aria-label="Suggested queries"
                  >
                    {suggestions.map((query) => {
                      const isMarcoWarehouseExercise =
                        persona?.id === 'marco' &&
                        showBuilderSessionGap &&
                        query === MARCO_BUILDER_SESSION_QUERY
                      return (
                        <button
                          key={query}
                          type="button"
                          data-testid={
                            isMarcoWarehouseExercise
                              ? 'boutique-hero-pill-marco-builder-session'
                              : undefined
                          }
                          aria-describedby={
                            isMarcoWarehouseExercise
                              ? 'boutique-hero-marco-exercise-hint'
                              : undefined
                          }
                          onClick={() => handlePillClick(query)}
                          className={[
                            'rounded-[10px] border transition-all duration-fade ease-out cursor-pointer',
                            'hover:border-[rgba(31,20,16,0.32)] hover:bg-[#f5eddf]',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(31,20,16,0.15)]',
                            isMarcoWarehouseExercise
                              ? 'border-dashed border-[rgba(196,69,54,0.55)] bg-[rgba(250,243,232,0.98)]'
                              : 'border border-[rgba(31,20,16,0.18)]',
                          ].join(' ')}
                          style={{
                            fontFamily: 'var(--sans)',
                            fontSize: '14px',
                            fontWeight: 400,
                            lineHeight: 1.35,
                            color: '#1f1410',
                            padding: '12px 20px',
                            background: isMarcoWarehouseExercise
                              ? 'rgba(255, 252, 247, 0.95)'
                              : 'var(--cream-warm)',
                            width: '185px',
                            minHeight: '58px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            textAlign: 'center',
                            flex: '0 0 auto',
                          }}
                        >
                          {query}
                        </button>
                      )
                    })}
                  </div>
                </>
              )}
            </div>

            {/* "Because" chip row — second line of suggestions that cite
                memory or live trend instead of canned queries. Reads as
                the agent's reasoning vocabulary: every chip names *why*
                it's surfacing, with a small kind label (memory · trend ·
                inventory) and an italic Fraunces clause. Clicking fires
                the chip's underlying query, same drawer flow as the
                suggestion pills above. */}
            {becauseChips.length > 0 && (
              <div
                data-testid="boutique-hero-because"
                className="mt-5 flex flex-col items-center gap-3"
                style={{ width: 'min(965px, calc(100vw - 32px))' }}
              >
                <div
                  className="inline-flex items-center gap-2"
                  style={{
                    fontFamily: 'var(--sans)',
                    fontSize: '11px',
                    fontWeight: 600,
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'rgba(31,20,16,0.55)',
                  }}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      width: 18,
                      height: 1,
                      background: 'rgba(31,20,16,0.25)',
                    }}
                  />
                  Because
                  <span
                    aria-hidden="true"
                    style={{
                      width: 18,
                      height: 1,
                      background: 'rgba(31,20,16,0.25)',
                    }}
                  />
                </div>
                <div className="flex flex-wrap justify-center gap-2.5">
                  {becauseChips.map((chip) => (
                    <button
                      key={`${chip.kind}-${chip.text}`}
                      type="button"
                      data-testid={`hero-because-${chip.kind}`}
                      onClick={() =>
                        handlePillClick(chip.query ?? chip.text)
                      }
                      className="
                        cursor-pointer transition-all duration-fade ease-out
                        hover:border-[rgba(168,66,58,0.45)] hover:bg-[rgba(255,250,240,0.95)]
                        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(168,66,58,0.25)]
                      "
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '10px 16px',
                        borderRadius: 999,
                        border: '1px dashed rgba(154, 52, 18, 0.35)',
                        background: 'rgba(255,250,240,0.78)',
                        fontFamily: "'Fraunces', Georgia, serif",
                        fontStyle: 'italic',
                        fontSize: '14.5px',
                        color: '#3b2f2f',
                        lineHeight: 1.35,
                      }}
                    >
                      <span
                        style={{
                          fontFamily: 'var(--sans)',
                          fontStyle: 'normal',
                          fontSize: '10px',
                          fontWeight: 600,
                          letterSpacing: '0.22em',
                          textTransform: 'uppercase',
                          color: 'var(--accent)',
                        }}
                      >
                        {BECAUSE_KIND_LABEL[chip.kind]}
                      </span>
                      <span>{chip.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

          </div>
      </div>
    </section>

    {/* Capabilities strip — replaces the old shipping/returns trust
        strip. Bold lead clauses name agent capabilities (reads live
        inventory · remembers your taste · cites every source · hands
        off to a human stylist), with the operational shipping line
        kept as a tail item so the reassurance still appears. Same
        cream-warm background, same burgundy dot separators, same
        whitespace — only the copy and emphasis change. */}
    <div
      data-testid="boutique-hero-trust"
      className="w-full border-b border-sand/40"
      style={{ background: 'var(--cream-warm)' }}
    >
      <div
        className="max-w-[1200px] mx-auto px-6 py-5 flex flex-wrap justify-center items-center gap-x-3 gap-y-2"
      >
        {TRUST_ITEMS.map((item, i) => (
          <span
            key={item.lead}
            className="inline-flex items-center whitespace-nowrap"
            style={{
              fontFamily: 'var(--sans)',
              fontSize: '12px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'rgba(31, 20, 16, 0.62)',
              fontWeight: 500,
            }}
          >
            {i > 0 && (
              <span
                aria-hidden="true"
                style={{
                  marginRight: '12px',
                  color: 'var(--accent)',
                  fontSize: '6px',
                  lineHeight: 1,
                }}
              >
                &#9679;
              </span>
            )}
            <span style={{ color: '#1f1410', fontWeight: 600 }}>
              {item.lead}
            </span>
            {item.trail ? (
              <>
                <span
                  aria-hidden="true"
                  style={{
                    margin: '0 8px',
                    color: 'rgba(31,20,16,0.35)',
                    fontSize: '6px',
                    lineHeight: 1,
                  }}
                >
                  &#9679;
                </span>
                <span>{item.trail}</span>
              </>
            ) : null}
          </span>
        ))}
      </div>
    </div>
    </>
  )
}
