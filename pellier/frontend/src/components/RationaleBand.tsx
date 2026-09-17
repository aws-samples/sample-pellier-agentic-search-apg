/**
 * RationaleBand — italic Fraunces pull-quote that explains the agent's
 * curation strategy for the grid below it. Sits between the curated
 * section eyebrow + headline and the product grid.
 *
 * The text describes the deterministic tag-ranking rule used for the
 * selected workshop profile. It does not imply live browsing or inventory
 * evidence that the participant has not generated.
 *
 * The storefront only needs the shopper-facing rationale sentence. Detailed
 * signal and tool provenance remains available inside each card disclosure.
 */
import { usePersona } from '../contexts/PersonaContext'

interface PersonaRationale {
  text: string
}

const PERSONA_RATIONALE: Record<string, PersonaRationale> = {
  marco: {
    text: 'Linen, leather, and pieces for the journey lead Marco’s edit. Open “Why this piece” for a closer look.',
  },
  anna: {
    text: 'Gifts, candles, and ceramics lead Anna’s edit. Open “Why this piece” for a closer look.',
  },
  theo: {
    text: 'Ceramics and pieces for a slower home lead Theo’s edit. Open “Why this piece” for a closer look.',
  },
  fresh: {
    text: 'Explore the collection, or choose Marco, Anna, or Theo to see their edit.',
  },
}

export default function RationaleBand() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? null
  const r = PERSONA_RATIONALE[personaId ?? 'fresh'] ?? PERSONA_RATIONALE.fresh

  return (
    <p
      data-testid="rationale-band"
      data-persona={personaId ?? 'fresh'}
      className="mt-3 max-w-[660px] font-sans text-[14px] leading-6 text-ink-soft"
    >
      {r.text}
    </p>
  )
}
