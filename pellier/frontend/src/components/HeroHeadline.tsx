/**
 * HeroHeadline — the editorial title block that sits above the HeroStage card.
 *
 * Three layers per mock:
 *   1. Small accent-terracotta eyebrow flanked by dot glyphs
 *      ("SUMMER EDIT \u00b7 NO. 06").
 *   2. Italic Fraunces two-line title ("Search," / "re:Imagined.") in ink.
 *   3. Italic Fraunces subhead in ink-soft.
 *
 * All strings come from `copy.ts`'s HERO_HEADLINE so the scanner governs them.
 */
import { HERO_HEADLINE } from '../copy'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'

export default function HeroHeadline() {
  return (
    <div
      data-testid="hero-headline"
      className="mx-auto w-full max-w-[1200px] px-4 pt-10 pb-6 text-center md:pt-14 md:pb-8"
    >
      <div
        data-testid="hero-headline-eyebrow"
        className="flex items-center justify-center gap-2 text-[11px] font-medium uppercase tracking-[0.24em]"
        style={{ color: ACCENT, fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        <span aria-hidden>&#9679;</span>
        <span>{HERO_HEADLINE.EYEBROW}</span>
        <span aria-hidden>&#9679;</span>
      </div>

      <h1
        data-testid="hero-headline-title"
        className="mt-4 font-[Fraunces] italic text-[40px] leading-[1] sm:text-[48px] md:text-[56px] lg:text-[64px]"
        style={{ color: INK, letterSpacing: '-0.01em', fontWeight: 500 }}
      >
        <span>{HERO_HEADLINE.TITLE_TOP}</span>{' '}
        <span>{HERO_HEADLINE.TITLE_BOTTOM}</span>
      </h1>

      <p
        data-testid="hero-headline-subhead"
        className="mx-auto mt-5 max-w-[660px] font-[Fraunces] italic text-[18px] leading-[1.55] md:text-[20px]"
        style={{ color: INK_SOFT, fontWeight: 600, letterSpacing: '-0.005em' }}
      >
        Tell Pellier what you're looking for.
        <br />
        Watch the pieces find you.
      </p>
    </div>
  )
}
