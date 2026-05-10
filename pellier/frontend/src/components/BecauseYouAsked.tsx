/**
 * BecauseYouAsked — "Because you asked..." editorial cards section.
 *
 * A 4-column CSS Grid of editorial teasers. Each card has a category
 * label, italic Fraunces title, and brief description.
 *
 * Personalization:
 *   - When a persona is active (Marco / Anna / Theo), the card
 *     lineup and the section headline both swap to a persona-tailored
 *     set from data/personaCurations.ts. Marco sees travel + linen
 *     edits, Anna sees gifting + apothecary, Theo sees slow-living +
 *     home rituals.
 *   - Fresh / anonymous visitors see the canonical editorial cards
 *     (Gifts / Performance / Linen / Home Rituals) — same as before.
 *   - A small "for <name>" chip appears in the header when a persona
 *     is active, so the personalization is visible, not silent.
 */
import { Card } from '../design/primitives'
import { usePersona } from '../contexts/PersonaContext'
import { editorialForPersona } from '../data/personaCurations'

const PERSONA_HEADLINES: Record<string, { eyebrow: string; headline: string }> = {
  marco: {
    eyebrow: 'Because you asked about travel',
    headline: 'Stories for the road.',
  },
  anna: {
    eyebrow: 'Because you asked about gifts',
    headline: 'Stories worth wrapping.',
  },
  theo: {
    eyebrow: 'Because you asked about slow craft',
    headline: 'Stories for quieter days.',
  },
}

const DEFAULT_HEADLINE = {
  eyebrow: 'Because you asked',
  headline: 'Stories worth exploring.',
}

export default function BecauseYouAsked() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? null

  const cards = editorialForPersona(personaId)
  const copy = (personaId && PERSONA_HEADLINES[personaId]) || DEFAULT_HEADLINE
  const isPersonalized = !!personaId && personaId !== 'fresh' && personaId in PERSONA_HEADLINES

  return (
    <section
      data-testid="because-you-asked"
      aria-label="Because you asked"
      className="w-full bg-cream-50 py-16 md:py-20 lg:py-24"
    >
      <div className="max-w-[1440px] mx-auto px-container-x">
        {/* Section header */}
        <div className="mb-12 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <p className="text-[11px] font-sans font-semibold tracking-[0.22em] uppercase text-ink-quiet mb-3">
              {copy.eyebrow}
            </p>
            <h2
              data-testid="because-you-asked-headline"
              className="font-display italic text-espresso"
              style={{
                fontSize: 'clamp(28px, 3.5vw, 44px)',
                lineHeight: 1.15,
                letterSpacing: '-0.01em',
                fontWeight: 400,
              }}
            >
              {copy.headline}
            </h2>
          </div>

          {/* Persona-active chip — gives attendees a visual cue that
              this band changed based on their persona pick. Fresh
              visitors see nothing, keeping the anonymous experience
              clean. */}
          {isPersonalized && persona && (
            <div
              data-testid="because-you-asked-persona-chip"
              className="inline-flex items-center gap-2 self-start md:self-end"
              style={{
                fontFamily: 'var(--sans)',
                fontSize: '11px',
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                fontWeight: 500,
                color: '#1f1410',
                padding: '6px 12px',
                borderRadius: 999,
                background: '#faf3e8',
                border: '1px solid rgba(31,20,16,0.12)',
              }}
            >
              <span aria-hidden style={{ color: '#a8423a', fontSize: '7px' }}>
                &#9679;
              </span>
              <span>For {persona.display_name.split(' ')[0]}</span>
            </div>
          )}
        </div>

        {/* 4-column grid */}
        <div
          data-testid="because-you-asked-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {cards.map((card) => (
            <Card key={card.category} className="p-6">
              {/* Category eyebrow */}
              <p className="text-[10px] font-sans font-semibold tracking-[0.2em] uppercase text-accent mb-3">
                {card.category}
              </p>

              {/* Title */}
              <h3
                className="font-display italic text-espresso mb-3"
                style={{
                  fontSize: 'clamp(18px, 1.5vw, 22px)',
                  lineHeight: 1.25,
                  fontWeight: 400,
                }}
              >
                {card.title}
              </h3>

              {/* Description */}
              <p
                className="font-sans text-ink-soft"
                style={{
                  fontSize: 'clamp(13px, 1vw, 14px)',
                  lineHeight: 1.6,
                }}
              >
                {card.description}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
