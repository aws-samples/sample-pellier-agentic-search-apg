/**
 * MemoryHandoffCard — workshop profile and session boundary.
 *
 * Sits between the editorial collection and the catalog. Surfaces the
 * selected profile's declared ranking seed and core scenario without turning
 * the storefront into an evidence dashboard.
 *
 * Clicking the CTA opens the chat drawer with a persona-appropriate
 * resume query.
 */
import { useUI } from '../contexts/UIContext'
import { usePersona } from '../contexts/PersonaContext'
import { memoryHandoffForPersona } from '../data/personaCurations'

const RESUME_QUERY: Record<string, string> = {
  marco: 'Pick up where I left off. Show me the linen pieces I was deciding between.',
  anna: 'Pick up where I left off. Open the gift shortlist I was building.',
  theo: 'Pick up where I left off and tell me about the bowl return.',
  fresh: 'A considered carry-all for a long weekend.',
}

export default function MemoryHandoffCard() {
  const { openDrawerWithQuery } = useUI()
  const { persona } = usePersona()
  const personaId = persona?.id ?? null
  if (!personaId) return null

  const content = memoryHandoffForPersona(personaId)
  const ctaLabel = content.cta ?? 'Open profile prompt'

  const handleCta = () => {
    const query = RESUME_QUERY[personaId ?? 'fresh'] ?? RESUME_QUERY.fresh
    openDrawerWithQuery(query)
  }

  return (
    <section
      data-testid="memory-handoff"
      data-persona={personaId ?? 'fresh'}
      aria-label="Workshop profile context"
      className="w-full bg-paper"
    >
      <div className="mx-auto max-w-[1120px] px-container-x py-8 md:py-10">
        <div
          data-testid="memory-handoff-card"
          className="
            flex flex-col gap-5 border-y border-line py-6
            md:flex-row md:items-center md:justify-between md:gap-10
          "
        >
          <div className="min-w-0 max-w-[760px]">
            <p
              data-testid="memory-handoff-eyebrow"
              className="mb-2 font-sans text-[13px] font-medium text-ink-2"
            >
              Workshop profile
            </p>
            <h3
              data-testid="memory-handoff-title"
              className="font-sans text-ink"
              style={{
                fontSize: 'clamp(20px, 2vw, 26px)',
                lineHeight: 1.25,
                fontWeight: 400,
                letterSpacing: 0,
                margin: 0,
              }}
            >
              {content.title}
            </h3>
            <p
              data-testid="memory-handoff-summary"
              className="mt-3 font-sans text-[14px] leading-6 text-ink-2"
            >
              {content.items.map((item) => item.text).join('. ')}.
            </p>
          </div>

          <button
            type="button"
            data-testid="memory-handoff-cta"
            onClick={handleCta}
            className="
              shrink-0 self-start rounded-full bg-ink px-5 py-3
              font-sans text-[14px] font-medium text-on-ink transition
              hover:bg-ink-2 focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-copper focus-visible:ring-offset-2 md:self-center
            "
            style={{
              whiteSpace: 'nowrap',
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
