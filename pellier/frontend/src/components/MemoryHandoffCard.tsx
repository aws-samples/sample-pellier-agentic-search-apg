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
          className="grid items-center gap-6 md:gap-8"
          style={{
            gridTemplateColumns: 'auto 1fr auto',
            background: '#fff8eb',
            border: '1px solid rgba(168,66,58,0.18)',
            borderRadius: 18,
            padding: '28px 32px',
            boxShadow: '0 8px 24px rgba(107,74,53,0.08)',
          }}
        >
          {/* Persona-keyed glyph — espresso disc with italic Fraunces "P" */}
          <div
            aria-hidden="true"
            style={{
              width: 54,
              height: 54,
              borderRadius: 999,
              background: '#3b2f2f',
              color: '#faf3e8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: "'Fraunces', Georgia, serif",
              fontStyle: 'italic',
              fontSize: 24,
              fontWeight: 500,
              flexShrink: 0,
            }}
          >
            P
          </div>

          {/* Body — eyebrow, italic title, tool-tagged memory list */}
          <div className="min-w-0">
            <p
              data-testid="memory-handoff-eyebrow"
              className="text-[11px] font-sans font-semibold tracking-[0.22em] uppercase mb-2"
              style={{ color: '#a8423a' }}
            >
              {content.eyebrow}
            </p>
            <h3
              data-testid="memory-handoff-title"
              className="font-display italic text-espresso"
              style={{
                fontSize: 'clamp(20px, 2vw, 26px)',
                lineHeight: 1.25,
                fontWeight: 400,
                margin: '0 0 12px',
              }}
            >
              {content.title}
            </h3>
            <ul
              data-testid="memory-handoff-list"
              className="flex flex-wrap gap-2.5 m-0 p-0 list-none mb-3"
            >
              {content.items.map((item) => (
                <li
                  key={item.tool}
                  className="inline-flex items-center gap-2"
                  style={{
                    padding: '8px 14px',
                    borderRadius: 999,
                    background: '#faf3e8',
                    border: '1px solid rgba(31,20,16,0.1)',
                    fontFamily: 'var(--sans)',
                    fontSize: 13,
                    color: '#1f1410',
                  }}
                >
                  {/* Trace pill — clickable, deep-links to the Atelier
                      route that explains this tool. Shoppers who want
                      to see how memory works can click straight in. */}
                  <TraceChip tool={item.tool} linkToAtelier compact />
                  <span>{item.text}</span>
                </li>
              ))}
            </ul>
            {/* Atelier handoff — for an attendee curious how durable
                memory actually works under the hood, this drops them on
                the Memory orbit explainer in one click. */}
            <SurfaceCrossLink
              direction="to-atelier"
              href="/atelier/memory"
              label="See how the agent's memory works"
            />
          </div>

          {/* CTA — opens the drawer with a persona-tailored resume query.
              Fresh visitors get a "Try a query" CTA that fires the same
              prompt as the first hero suggestion pill. */}
          <button
            type="button"
            data-testid="memory-handoff-cta"
            onClick={handleCta}
            className="rounded-full font-sans font-medium transition-colors duration-fade hover:bg-dusk cursor-pointer"
            style={{
              background: '#3b2f2f',
              color: '#faf3e8',
              padding: '14px 22px',
              fontSize: 14,
              border: 0,
              whiteSpace: 'nowrap',
              alignSelf: isFresh ? 'flex-end' : 'center',
            }}
          >
            {ctaLabel} →
          </button>
        </div>
      </div>
    </section>
  )
}
