/**
 * Footer — masthead row, three live columns, disclaimer, legal strip.
 *
 * Every link points at a route the router serves:
 *
 *   - Masthead:     the wordmark at 36px, demo payment marks right.
 *   - Brand column: tagline plus what this storefront is, as a list.
 *   - Explore:      The floor (`/#shop`), Stories, About.
 *   - Storyboard:   blurb plus a real link to `/storyboard`.
 *   - Disclaimer:   states that nothing is charged, the catalog is synthetic,
 *                   and AI-generated imagery is illustrative.
 *   - Legal strip:  copyright, licence, team credit, source link. No Privacy/
 *                   Terms/Accessibility stubs.
 *
 * The footer keeps official marks inside an explicitly disclosed demo
 * checkout: no payment is processed, and no card is charged.
 *
 * Copy from `FOOTER` in copy.ts.
 */
import { Link } from 'react-router-dom'

import { FOOTER } from '../copy'
import Wordmark from './Wordmark'

export default function Footer() {
  const year = new Date().getFullYear()
  const copyrightLine = `${FOOTER.BOTTOM_STRIP.COPYRIGHT} ${year}`

  return (
    <footer
      data-testid="footer"
      role="contentinfo"
      className="border-t border-line bg-page font-sans text-ink"
      style={{
        padding: '56px 0 32px',
      }}
    >
      <div className="pellier-edit-shell">
        <Masthead />
        <div
          data-testid="footer-columns"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 48,
            paddingBottom: 40,
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
        </div>
        <Disclaimer />
        <BottomStrip
          copyrightLine={copyrightLine}
          rights={FOOTER.BOTTOM_STRIP.RIGHTS}
          license={FOOTER.BOTTOM_STRIP.LICENSE}
          attribution={FOOTER.BOTTOM_STRIP.ATTRIBUTION}
          githubUrl={FOOTER.BOTTOM_STRIP.GITHUB_URL}
          githubLabel={FOOTER.BOTTOM_STRIP.GITHUB_LABEL}
        />
      </div>
    </footer>
  )
}

/**
 * Brand lockup opposite the disclosed demo payment strip. This is the row that
 * makes the footer read as a shopfront rather than a sitemap.
 */
function Masthead() {
  return (
    <div
      data-testid="footer-masthead"
      className="flex flex-col gap-5 pb-10 sm:flex-row sm:items-center sm:justify-between"
    >
      <Wordmark size="footer" />
      <CheckoutTrust />
    </div>
  )
}

function CheckoutTrust() {
  return (
    <div
      data-testid="footer-checkout-trust"
      className="flex flex-col gap-2 sm:items-end"
    >
      <span
        data-testid="footer-checkout-label"
        className="font-sans text-[12px] text-muted"
      >
        {FOOTER.CHECKOUT.LABEL}
      </span>
      <ul
        aria-label={FOOTER.CHECKOUT.ARIA_LABEL}
        className="grid w-fit grid-cols-3 gap-1.5 m-0 p-0 list-none sm:flex sm:flex-wrap sm:justify-end"
      >
        {FOOTER.CHECKOUT.PAYMENT_METHODS.map((method) => (
          <li
            key={method.id}
            className="flex h-9 shrink-0 items-center justify-center rounded-[6px] border border-line bg-paper px-2.5"
          >
            <img
              alt=""
              aria-hidden="true"
              className="h-5 w-auto object-contain"
              height={20}
              src={`/assets/icons/payment/${method.id}.svg`}
            />
            <span className="sr-only">{method.label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function BrandColumn() {
  return (
    <section
      data-testid="footer-column-brand"
      aria-label="Pellier"
      className="flex flex-col gap-4"
    >
      <p
        data-testid="footer-brand-tagline"
        className="text-[13px] leading-relaxed text-ink-2 m-0 max-w-[260px]"
      >
        {FOOTER.BRAND.TAGLINE}
      </p>
      <ul
        data-testid="footer-service-items"
        role="list"
        className="flex flex-col gap-2 m-0 p-0 list-none"
      >
        {FOOTER.BOTTOM_STRIP.SERVICE_ITEMS.map((item) => (
          <li
            key={item}
            className="flex items-start gap-2 text-xs leading-relaxed text-muted"
          >
            <span
              aria-hidden="true"
              className="mt-[6px] block h-1.5 w-1.5 shrink-0 rounded-full bg-line-strong"
            />
            {item}
          </li>
        ))}
      </ul>
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
        className="font-sans text-[13px] font-medium text-ink m-0"
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
              className="inline-flex min-h-[44px] min-w-[44px] items-center py-1 text-sm text-ink-2 no-underline transition-colors duration-fade ease-out hover:text-ink"
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
        className="font-sans text-[13px] font-medium text-ink m-0"
      >
        {heading}
      </h3>
      <p className="font-sans text-[15px] leading-[1.55] text-ink-2 m-0">
        {copy}
      </p>
      <Link
        to={ctaHref}
        data-testid={`${testId}-cta`}
        className="pellier-action-quiet mt-1 w-fit text-[13px] no-underline"
      >
        {ctaLabel}
      </Link>
    </section>
  )
}

/**
 * Said outright, above the legal strip rather than buried in it. A storefront
 * this finished invites the assumption that it transacts and that its reviews
 * and stock counts are real; both are false and cheap to state.
 */
function Disclaimer() {
  return (
    <p
      data-testid="footer-disclaimer"
      className="font-sans text-xs leading-relaxed text-muted m-0 max-w-[720px] pt-8 border-t border-line"
    >
      {FOOTER.DISCLAIMER}
    </p>
  )
}

interface BottomStripProps {
  copyrightLine: string
  rights: string
  license: string
  attribution: string
  githubUrl: string
  githubLabel: string
}

function BottomStrip({
  copyrightLine,
  rights,
  license,
  attribution,
  githubUrl,
  githubLabel,
}: BottomStripProps) {
  return (
    <div
      data-testid="footer-bottom-strip"
      className="flex flex-col items-start gap-2 pt-6 sm:flex-row sm:items-center sm:justify-between"
    >
      <span
        data-testid="footer-copyright"
        className="text-xs text-muted"
      >
        {copyrightLine}
      </span>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span
          data-testid="footer-legal"
          className="flex flex-wrap gap-x-3 font-sans text-xs text-muted"
        >
          <span>{rights}</span>
          <span>{license}</span>
          <span data-testid="footer-attribution">{attribution}</span>
        </span>
        <a
          data-testid="footer-github-link"
          href={githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={githubLabel}
          title={githubLabel}
          className="group inline-flex min-h-[44px] min-w-[44px] items-center justify-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-copper"
        >
          <img
            data-testid="footer-github-icon"
            src="/assets/icons/github-mark.svg"
            alt=""
            aria-hidden="true"
            width={18}
            height={18}
            className="pellier-github-mark h-[18px] w-[18px] opacity-65 transition-opacity group-hover:opacity-100"
          />
        </a>
      </div>
    </div>
  )
}
