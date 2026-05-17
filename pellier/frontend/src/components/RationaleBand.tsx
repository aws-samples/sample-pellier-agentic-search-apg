/**
 * RationaleBand — italic Fraunces pull-quote that explains the agent's
 * curation strategy for the grid below it. Sits between the curated
 * section eyebrow + headline and the product grid.
 *
 * For fresh visitors the rationale leads with what the agent will do
 * once it has signal ("I'll learn as we go..."). For returning personas
 * it leads with what the agent already used to shape the grid (saved
 * item, palette, recent trend). The same layout in every persona keeps
 * the page rhythm steady.
 *
 * Visual: thin terracotta left rule + `you said …` eyebrow + the
 * rationale clause. No new tokens — same accent / espresso / Fraunces.
 */
import { usePersona } from '../contexts/PersonaContext'
import { SurfaceCrossLink } from '../shared'

interface PersonaRationale {
  /** Eyebrow above the rationale ("you said …" / "you've been browsing …"). */
  eyebrow: string
  /** Italic body line — single sentence preferred. */
  text: string
}

const PERSONA_RATIONALE: Record<string, PersonaRationale> = {
  marco: {
    eyebrow: 'You said · pieces that travel well',
    text: 'I started with what you saved last visit, then pulled three pieces in the same weight and palette. Each card below shows why it made the cut.',
  },
  anna: {
    eyebrow: "You've been browsing · gifts that arrive wrapped",
    text: 'I narrowed to pieces that pair cleanly with the candles you saved, and flagged anything that just restocked. Each card cites the signal.',
  },
  theo: {
    eyebrow: "You've been browsing · slow-craft objects",
    text: 'I leaned into the makers and palettes you opened twice last week, then surfaced one bowl back from the kiln this morning. Reasoning lives on each card.',
  },
  fresh: {
    eyebrow: 'New here · I learn as we go',
    text: "I'll lead with what's quietly trending and pieces our editors are reaching for this week. Save anything that catches your eye and the grid will sharpen on the next visit.",
  },
}

export default function RationaleBand() {
  const { persona } = usePersona()
  const personaId = persona?.id ?? null
  const r = PERSONA_RATIONALE[personaId ?? 'fresh'] ?? PERSONA_RATIONALE.fresh

  return (
    <div
      data-testid="rationale-band"
      data-persona={personaId ?? 'fresh'}
      className="max-w-[1440px] mx-auto px-container-x mb-7 md:mb-9"
    >
      <p
        className="font-display italic text-espresso m-0"
        style={{
          fontSize: 'clamp(17px, 1.4vw, 19px)',
          lineHeight: 1.55,
          maxWidth: 780,
          borderLeft: '2px solid color-mix(in srgb, var(--accent) 85%, transparent)',
          padding: '6px 0 6px 18px',
        }}
      >
        <span
          className="font-mono"
          style={{
            display: 'block',
            fontStyle: 'normal',
            fontWeight: 600,
            fontSize: 'var(--dl-fs-eyebrow)',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: 8,
          }}
        >
          {r.eyebrow}
        </span>
        {r.text}
      </p>
      {/* "How this works" → drops the developer into the Atelier's
          Architecture index, where every concept the rationale touches
          (memory, tools, agents, routing) is explained one-screen-deep.
          Sits at the foot of the rationale so it feels like a
          continuation of the agent's voice, not a marketing CTA. */}
      <div className="mt-3 ml-5">
        <SurfaceCrossLink
          direction="to-atelier"
          href="/atelier/architecture"
          label="How this works · in the Atelier"
          italic={false}
        />
      </div>
    </div>
  )
}
