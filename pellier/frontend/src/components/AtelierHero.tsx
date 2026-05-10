/**
 * AtelierHero — editorial hero above the /workshop split.
 *
 * Mirrors the storefront's hero register (kicker · display italic ·
 * epigraph) so the two surfaces read as siblings rather than a
 * boutique paired with a developer dashboard.
 *
 * Sits full-width above the chat-left / tabs-right split; the split
 * itself stays inside the main area below. Paired with
 * ``AtmosphereStrip`` and ``MetricsRow`` to make the hero zone.
 */
import { SURFACE_TOGGLE } from '../copy'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'

export default function AtelierHero({ editionNumber = 6 }: { editionNumber?: number }) {
  const label = `${SURFACE_TOGGLE.ATELIER.toUpperCase()} · NO. ${String(editionNumber).padStart(
    2,
    '0',
  )}`
  return (
    <section
      data-testid="atelier-hero"
      className="px-6 pt-6 pb-8 text-center"
    >
      <p
        className="font-mono text-[11px] font-medium uppercase mb-5 flex items-center justify-center gap-2"
        style={{ color: ACCENT, letterSpacing: '0.22em' }}
      >
        <span
          aria-hidden
          className="inline-block w-[5px] h-[5px] rounded-full"
          style={{ background: ACCENT }}
        />
        <span>{label}</span>
        <span
          aria-hidden
          className="inline-block w-[5px] h-[5px] rounded-full"
          style={{ background: ACCENT }}
        />
      </p>
      <h1
        className="text-[54px] md:text-[60px] leading-[1] m-0"
        style={{
          color: INK,
          fontFamily: 'Fraunces, Georgia, serif',
          fontWeight: 400,
          fontStyle: 'italic',
          letterSpacing: '-0.02em',
        }}
      >
        The Atelier.
      </h1>
      <p
        className="text-[16px] leading-[1.6] max-w-[620px] mx-auto mt-5"
        style={{
          color: INK_SOFT,
          fontFamily: 'Fraunces, Georgia, serif',
          fontStyle: 'italic',
          fontWeight: 600,
        }}
      >
        Where Agents think aloud. Every step of the reasoning, on display.
      </p>
    </section>
  )
}
