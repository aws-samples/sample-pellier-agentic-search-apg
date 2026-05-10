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
import { heroPillsForPersona } from '../data/personaCurations'
import { useVoiceSearch } from '../hooks/useVoiceSearch'

// Per-persona hero images (landscape, in public/products/).
// Falls back to the fresh hero for unknown personas.
const PERSONA_HERO_IMAGES: Record<string, string> = {
  fresh: '/products/hero-fresh-2.png',
  marco: '/products/hero-marco.png',
  anna: '/products/hero-anna.png',
  theo: '/products/hero-theo.png',
}

const TRUST_ITEMS = [
  'Curated by hand',
  'Live inventory',
  'Free shipping over $150',
  'Ships in 1\u20132 days',
  'Easy returns',
]

export default function BoutiqueHero() {
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const suggestions = heroPillsForPersona(persona?.id)
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

  const handleMicClick = useCallback(() => {
    const trimmed = searchValue.trim()
    if (!trimmed) return
    openDrawerWithQuery(trimmed)
    setSearchValue('')
  }, [searchValue, openDrawerWithQuery])

  const handlePillClick = useCallback(
    (query: string) => {
      openDrawerWithQuery(query)
    },
    [openDrawerWithQuery],
  )

  return (
    <>
    <section
      data-testid="boutique-hero"
      aria-label="Search and discover"
      className="relative h-[78vh] min-h-[720px] overflow-hidden"
    >
      {/* ── Full-bleed photograph — pushed left so text reads clean ── */}
      <img
        src={heroImage}
        alt="Editorial boutique hero"
        className="absolute inset-0 h-full w-full object-cover object-[20%_center]"
      />

      {/* ── Soft gradient overlay for text readability ── */}
      <div
        className="absolute inset-0 bg-gradient-to-r from-transparent via-[#f7f0e6]/20 to-[#f7f0e6]/45"
        aria-hidden="true"
      />

      {/* ── Typography overlay — centered content ── */}
      <div className="relative z-10 mx-auto flex h-full max-w-7xl items-center justify-center px-8">
          <div
            className="w-full max-w-4xl py-12 md:py-0
                       flex flex-col items-center text-center"
          >
            {/* Eyebrow — "• SUMMER EDIT • NO. 06 •" — matches
                WeekendEditorial eyebrow type treatment exactly, with
                burgundy dot separators. */}
            <div
              data-testid="boutique-hero-eyebrow"
              className="flex items-center gap-3 mb-5 text-[13px] font-sans font-semibold tracking-[0.22em] uppercase text-espresso"
            >
              <span aria-hidden="true" style={{ color: '#a8423a', fontSize: '9px' }}>&#9679;</span>
              <span>Summer Edit</span>
              <span aria-hidden="true" style={{ color: '#a8423a', fontSize: '5px' }}>&#9679;</span>
              <span>No. 06</span>
              <span aria-hidden="true" style={{ color: '#a8423a', fontSize: '9px' }}>&#9679;</span>
            </div>

            {/* Headline — same Fraunces italic treatment as
                WeekendEditorial, but sized up for hero prominence. */}
            <h1
              data-testid="boutique-hero-headline"
              className="whitespace-nowrap font-display italic text-espresso"
              style={{
                fontSize: 'clamp(44px, 6vw, 76px)',
                lineHeight: 1.05,
                letterSpacing: '-0.015em',
                fontWeight: 400,
              }}
            >
              Search, re:Engineered.
            </h1>

            {/* Subheadline — same Inter sans / ink-soft treatment as
                WeekendEditorial subhead, sized up for hero prominence. */}
            <p
              data-testid="boutique-hero-subheadline"
              className="mx-auto mt-6 max-w-[600px] font-sans text-ink-soft"
              style={{
                fontSize: 'clamp(17px, 1.4vw, 21px)',
                lineHeight: 1.55,
              }}
            >
              Tell Blaize what you&rsquo;re looking for.
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
                  className="absolute left-6 top-1/2 -translate-y-1/2 pointer-events-none z-10"
                  style={{ color: '#a8423a' }}
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
                  placeholder={isListening ? 'Listening...' : 'Ask Blaize anything...'}
                  aria-label="Ask Blaize anything"
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
                    background: isListening ? '#a8423a' : '#1f1410',
                    color: '#faf3e8',
                    cursor: 'pointer',
                    // Pulsing ring when listening
                    boxShadow: isListening
                      ? '0 0 0 4px rgba(168, 66, 58, 0.3), 0 0 0 8px rgba(168, 66, 58, 0.15)'
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

            {/* "Try asking" label */}
            <div
              data-testid="boutique-hero-try-asking"
              className="mt-6 md:mt-8"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: '16px',
                fontWeight: 500,
                color: '#1f1410',
              }}
            >
              Try asking
            </div>

            {/* Suggestion chips — 5 in a row at desktop, wrap to 3+2
                or 2+2+1 at narrower widths. Text wraps to 2 lines
                inside each chip. Matches the reference's compact grid.
                `flex-wrap` (instead of `flex-nowrap`) prevents the row
                from spilling past the hero section's overflow:hidden
                bounds — at <1024px the first / last pill were getting
                clipped to "ft for runs" / "a cozy".

                The pill row breaks out of the form's max-w-4xl wrapper
                (896px) because 5 pills + gaps = 965px. We use clamp()
                so the row caps at 965px on desktop and shrinks with
                the viewport on smaller screens. */}
            <div
              data-testid="boutique-hero-pills"
              className="mt-4 flex flex-wrap justify-center gap-2.5"
              role="listbox"
              aria-label="Suggested queries"
              style={{
                width: 'min(965px, calc(100vw - 32px))',
              }}
            >
              {suggestions.map((query) => (
                <button
                  key={query}
                  type="button"
                  onClick={() => handlePillClick(query)}
                  className="
                    rounded-[10px]
                    border border-[rgba(31,20,16,0.18)]
                    hover:border-[rgba(31,20,16,0.32)] hover:bg-[#f5eddf]
                    transition-all duration-fade ease-out
                    cursor-pointer
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(31,20,16,0.15)]
                  "
                  style={{
                    fontFamily: 'var(--sans)',
                    fontSize: '14px',
                    fontWeight: 400,
                    lineHeight: 1.35,
                    color: '#1f1410',
                    padding: '12px 20px',
                    background: '#faf3e8',
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
              ))}
            </div>

          </div>
      </div>
    </section>

    {/* Trust strip — sits on the cream page background directly below
        the photograph. Single line with burgundy dot separators and
        small icons matching the reference. */}
    <div
      data-testid="boutique-hero-trust"
      className="w-full border-b border-sand/40"
      style={{ background: '#faf3e8' }}
    >
      <div
        className="max-w-[1200px] mx-auto px-6 py-5 flex flex-wrap justify-center items-center gap-x-3 gap-y-2"
      >
        {TRUST_ITEMS.map((item, i) => (
          <span
            key={item}
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
                  color: '#a8423a',
                  fontSize: '6px',
                  lineHeight: 1,
                }}
              >
                &#9679;
              </span>
            )}
            {item}
          </span>
        ))}
      </div>
    </div>
    </>
  )
}
