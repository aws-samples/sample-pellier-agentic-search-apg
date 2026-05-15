/**
 * Footer — brand + three live columns + bottom strip.
 *
 * Earlier footer shipped with five columns and a newsletter form.
 * Every link pointed to a placeholder route. Replaced with three
 * live surfaces that map 1:1 to routes that exist in the router:
 *
 *   - Brand column: circular P mark + "Pellier" + tagline.
 *   - Explore:      The floor (`/#shop`), Discover, Storyboard.
 *   - Storyboard:   Italic blurb + a real link to `/storyboard`.
 *   - Atelier:      Italic blurb + a real link to `/atelier`.
 *   - Bottom strip: Copyright + current year. No Privacy/Terms/
 *                   Accessibility stubs — those were the same dead
 *                   links this rewrite is eliminating. Right-hand
 *                   attribution from `FOOTER.BOTTOM_STRIP.ATTRIBUTION`.
 *
 * Copy from `FOOTER` in copy.ts.
 *
 * Phase 2 redesign: replaced all hardcoded hex color constants with
 * Tailwind token classes. Uses fluid container, font-display / font-sans
 * utilities, border-sand/50 for borders, and duration-fade for transitions.
 */
import { Link } from 'react-router-dom'

import { FOOTER } from '../copy'

export default function Footer() {
  const year = new Date().getFullYear()
  const copyrightLine = `${FOOTER.BOTTOM_STRIP.COPYRIGHT} ${year}`

  return (
    <footer
      data-testid="footer"
      role="contentinfo"
      className="bg-sand text-espresso font-sans border-t border-sand/50"
      style={{
        padding: '72px 24px 32px',
      }}
    >
      <div className="max-w-[1440px] mx-auto px-container-x">
        <div
          data-testid="footer-columns"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 48,
            paddingBottom: 48,
          }}
        >
          <BrandColumn />
          <ExploreColumn />
          <EditorialColumn
            testId="footer-column-storyboard"
            heading={FOOTER.STORYBOARD.HEADING}
            copy={FOOTER.STORYBOARD.COPY}
            ctaLabel={FOOTER.STORYBOARD.CTA_LABEL}
            ctaHref={FOOTER.STORYBOARD.CTA_HREF}
          />
          <EditorialColumn
            testId="footer-column-atelier"
            heading={FOOTER.ATELIER.HEADING}
            copy={FOOTER.ATELIER.COPY}
            ctaLabel={FOOTER.ATELIER.CTA_LABEL}
            ctaHref={FOOTER.ATELIER.CTA_HREF}
          />
        </div>
        <BottomStrip
          copyrightLine={copyrightLine}
          attribution={FOOTER.BOTTOM_STRIP.ATTRIBUTION}
        />
      </div>
    </footer>
  )
}

function BrandColumn() {
  return (
    <section
      data-testid="footer-column-brand"
      aria-label="Pellier"
      className="flex flex-col gap-4"
    >
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="pellier-logo-chip bg-espresso text-cream-50"
        >
          P
        </span>
        <span className="font-display text-xl font-medium tracking-tight">
          Pellier
        </span>
      </div>
      <p
        data-testid="footer-brand-tagline"
        className="text-[13px] leading-relaxed text-ink-soft m-0 max-w-[260px]"
      >
        {FOOTER.BRAND.TAGLINE}
      </p>
    </section>
  )
}

function ExploreColumn() {
  return (
    <section
      data-testid="footer-column-explore"
      aria-labelledby="footer-column-explore-heading"
      className="flex flex-col gap-3.5"
    >
      <h3
        id="footer-column-explore-heading"
        className="font-sans text-[11px] font-semibold tracking-[0.18em] uppercase text-ink-quiet m-0"
      >
        {FOOTER.EXPLORE.HEADING}
      </h3>
      <ul
        role="list"
        className="flex flex-col gap-2.5 m-0 p-0 list-none"
      >
        {FOOTER.EXPLORE.ITEMS.map(({ label, href }) => (
          <li key={label}>
            <Link
              to={href}
              data-testid={`footer-explore-link-${label.toLowerCase().replace(/\s+/g, '-')}`}
              className="text-espresso text-sm no-underline transition-colors duration-fade ease-out hover:text-accent"
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

interface EditorialColumnProps {
  testId: string
  heading: string
  copy: string
  ctaLabel: string
  ctaHref: string
}

function EditorialColumn({
  testId,
  heading,
  copy,
  ctaLabel,
  ctaHref,
}: EditorialColumnProps) {
  return (
    <section
      data-testid={testId}
      aria-labelledby={`${testId}-heading`}
      className="flex flex-col gap-3.5"
    >
      <h3
        id={`${testId}-heading`}
        className="font-sans text-[11px] font-semibold tracking-[0.18em] uppercase text-ink-quiet m-0"
      >
        {heading}
      </h3>
      <p className="font-display italic font-normal text-[15px] leading-[1.55] text-espresso m-0">
        {copy}
      </p>
      <Link
        to={ctaHref}
        data-testid={`${testId}-cta`}
        className="font-sans text-[13px] font-medium tracking-tight text-accent no-underline mt-1 inline-flex items-center gap-1.5 transition-all duration-fade ease-out hover:underline"
      >
        {ctaLabel}
        <span aria-hidden>&rarr;</span>
      </Link>
    </section>
  )
}

interface BottomStripProps {
  copyrightLine: string
  attribution: string
}

function BottomStrip({ copyrightLine, attribution }: BottomStripProps) {
  return (
    <div
      data-testid="footer-bottom-strip"
      className="flex items-center justify-between gap-4 pt-6 border-t border-sand/50"
    >
      <span
        data-testid="footer-copyright"
        className="text-xs text-ink-quiet"
      >
        {copyrightLine}
      </span>
      <span
        data-testid="footer-attribution"
        className="font-sans text-xs text-ink-quiet tracking-tight"
      >
        {attribution}
      </span>
    </div>
  )
}
