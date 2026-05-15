/**
 * MemoryHandoffCard — "Pick up where I left off."
 *
 * Sits between the BoutiqueWelcomeBand and the Weekend Edit. Surfaces
 * what the agent remembers about a returning shopper (saved item,
 * holds in bag, restock watches) with each line tagged by the tool
 * that produced it (`memory.recall`, `cart.holds`, `inventory.watch`).
 * For fresh visitors, the same slot reads as a "I'll learn as we go"
 * onboarding card so the layout rhythm stays consistent persona-to-
 * persona.
 *
 * Reuses the existing daylight palette — cream-warm background, accent
 * border, espresso italic title, mono tool stamps. No new tokens.
 *
 * Clicking the CTA opens the chat drawer with a persona-appropriate
 * resume query.
 */
import { useUI } from '../contexts/UIContext'
import { usePersona } from '../contexts/PersonaContext'
import { memoryHandoffForPersona } from '../data/personaCurations'
import { TraceChip, SurfaceCrossLink } from '../shared'

const RESUME_QUERY: Record<string, string> = {
  marco: 'Pick up where I left off — show me the linen pieces I was deciding between',
  anna: 'Pick up where I left off — the gift shortlist I was building',
  theo: 'Pick up where I left off — and tell me about the bowl return',
  fresh: 'A thoughtful gift for someone who runs',
}

export default function MemoryHandoffCard() {
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const personaId = persona?.id ?? null
  const content = memoryHandoffForPersona(personaId)
  const ctaLabel = content.cta ?? 'Pick up where I left off'
  const isFresh = !personaId || personaId === 'fresh'

  const handleCta = () => {
    const query = RESUME_QUERY[personaId ?? 'fresh'] ?? RESUME_QUERY.fresh
    openDrawerWithQuery(query)
  }

  return (
    <section
      data-testid="memory-handoff"
      data-persona={personaId ?? 'fresh'}
      aria-label="Pick up where you left off"
      className="w-full bg-cream-50"
    >
      <div className="max-w-[1100px] mx-auto px-container-x py-10 md:py-12">
        <div
          data-testid="memory-handoff-card"
          className="grid items-start gap-6 md:gap-8 shadow-warm-sm"
          style={{
            gridTemplateColumns: 'auto 1fr auto',
            background: 'color-mix(in srgb, var(--cream-warm) 65%, #ffffff)',
            border: '1px solid color-mix(in srgb, var(--accent) 18%, var(--rule-1))',
            borderRadius: 18,
            padding: '28px 32px',
          }}
        >
          {/* Persona-keyed glyph — espresso disc + cream "P" (matches header wordmark). */}
          <div
            aria-hidden="true"
            style={{
              width: 54,
              height: 54,
              borderRadius: 999,
              background: 'var(--ink)',
              color: 'var(--cream-warm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--sans)',
              fontStyle: 'normal',
              fontSize: 22,
              fontWeight: 600,
              letterSpacing: '-0.02em',
              flexShrink: 0,
            }}
          >
            P
          </div>

          {/* Body — mono eyebrow, serif title, tool row + prose row */}
          <div className="min-w-0">
            <p
              data-testid="memory-handoff-eyebrow"
              className="font-mono font-semibold uppercase mb-2"
              style={{
                fontSize: 'var(--dl-fs-eyebrow)',
                letterSpacing: '0.12em',
                color: 'var(--accent)',
              }}
            >
              {content.eyebrow}
            </p>
            <h3
              data-testid="memory-handoff-title"
              className="font-display italic text-espresso"
              style={{
                fontSize: 'clamp(20px, 2vw, 26px)',
                lineHeight: 1.3,
                fontWeight: 400,
                letterSpacing: '-0.02em',
                margin: '0 0 14px',
              }}
            >
              {content.title}
            </h3>
            <ul
              data-testid="memory-handoff-list"
              className="m-0 mb-4 list-none divide-y divide-warm p-0"
            >
              {content.items.map((item) => (
                <li
                  key={item.tool}
                  className="flex flex-wrap items-start gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0"
                >
                  {/* Trace pill — deep-links to the Atelier explainer */}
                  <TraceChip tool={item.tool} linkToAtelier compact />
                  <p
                    className="m-0 min-w-0 flex-1 font-sans text-ink-soft"
                    style={{
                      fontSize: 14,
                      lineHeight: 1.55,
                      letterSpacing: '-0.01em',
                      fontWeight: 400,
                    }}
                  >
                    {item.text}
                  </p>
                </li>
              ))}
            </ul>
            {/* Atelier handoff — for an attendee curious how durable
                memory actually works under the hood, this drops them on
                the Memory orbit explainer in one click. */}
            <div className="mt-1">
              <SurfaceCrossLink
                direction="to-atelier"
                href="/atelier/memory"
                label="See how the agent's memory works"
              />
            </div>
          </div>

          {/* CTA — opens the drawer with a persona-tailored resume query.
              Fresh visitors get a "Try a query" CTA that fires the same
              prompt as the first hero suggestion pill. */}
          <button
            type="button"
            data-testid="memory-handoff-cta"
            onClick={handleCta}
            className="rounded-full font-sans font-medium tracking-wide transition-colors duration-fade hover:opacity-95 cursor-pointer"
            style={{
              background: 'var(--ink)',
              color: 'var(--cream-warm)',
              padding: '14px 22px',
              fontSize: 14,
              letterSpacing: '0.04em',
              border: 0,
              whiteSpace: 'nowrap',
              alignSelf: isFresh ? 'flex-end' : 'center',
            }}
          >
            {ctaLabel}
            <span aria-hidden="true" style={{ marginLeft: 6 }}>
              →
            </span>
          </button>
        </div>
      </div>
    </section>
  )
}
