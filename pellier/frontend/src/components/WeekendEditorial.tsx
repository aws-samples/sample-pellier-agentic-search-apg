/**
 * WeekendEditorial — "Weekend, re:defined." editorial band.
 *
 * A full-width editorial section that creates visual rhythm between
 * the hero and the product grid. Simple eyebrow + headline + subheadline
 * on a slightly different background tone (cream-warm / sand).
 */

export default function WeekendEditorial() {
  return (
    <section
      data-testid="weekend-editorial"
      aria-label="Weekend editorial"
      className="w-full"
      style={{
        background:
          'linear-gradient(180deg, #F5E8D3 0%, #F7F3EE 100%)',
      }}
    >
      <div className="max-w-[1440px] mx-auto px-container-x py-16 md:py-20 lg:py-24 text-center">
        {/* Eyebrow */}
        <p
          data-testid="weekend-editorial-eyebrow"
          className="text-[11px] font-sans font-semibold tracking-[0.22em] uppercase text-ink-quiet mb-4"
        >
          Weekend Edit
        </p>

        {/* Headline */}
        <h2
          data-testid="weekend-editorial-headline"
          className="font-display italic text-espresso"
          style={{
            fontSize: 'clamp(32px, 4.5vw, 56px)',
            lineHeight: 1.1,
            letterSpacing: '-0.01em',
            fontWeight: 400,
          }}
        >
          Weekend, re:defined.
        </h2>

        {/* Subheadline */}
        <p
          data-testid="weekend-editorial-subheadline"
          className="mx-auto mt-5 max-w-[540px] font-sans text-ink-soft"
          style={{
            fontSize: 'clamp(14px, 1.1vw, 16px)',
            lineHeight: 1.65,
          }}
        >
          Pieces that move with you from morning markets to golden-hour
          terraces. Linen, leather, ceramic — the weekend wardrobe,
          considered.
        </p>
      </div>
    </section>
  )
}
