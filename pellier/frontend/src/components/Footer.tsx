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
            className="flex h-9 shrink-0 items-center justify-center rounded-[6px] border border-line bg-[var(--dl-mark-ground)] px-2.5"
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
          className="group inline-flex min-h-[44px] min-w-[44px] items-center justify-center text-muted transition-colors hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-copper"
        >
          <GitHubMark />
        </a>
      </div>
    </div>
  )
}

/**
 * The GitHub mark, drawn inline so it takes the link's token color in both
 * themes; an <img> keeps the file's own black fill. The path is
 * `public/assets/icons/github-mark.svg` (Primer Octicons, MIT; see
 * GITHUB-MARK-LICENSE.txt beside it).
 */
function GitHubMark() {
  return (
    <svg
      data-testid="footer-github-icon"
      viewBox="0 0 24 24"
      width={18}
      height={18}
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      className="h-[18px] w-[18px]"
    >
      <path d="M10.226 17.284c-2.965-.36-5.054-2.493-5.054-5.256 0-1.123.404-2.336 1.078-3.144-.292-.741-.247-2.314.09-2.965.898-.112 2.111.36 2.83 1.01.853-.269 1.752-.404 2.853-.404 1.1 0 1.999.135 2.807.382.696-.629 1.932-1.1 2.83-.988.315.606.36 2.179.067 2.942.72.854 1.101 2 1.101 3.167 0 2.763-2.089 4.852-5.098 5.234.763.494 1.28 1.572 1.28 2.807v2.336c0 .674.561 1.056 1.235.786 4.066-1.55 7.255-5.615 7.255-10.646C23.5 6.188 18.334 1 11.978 1 5.62 1 .5 6.188.5 12.545c0 4.986 3.167 9.12 7.435 10.669.606.225 1.19-.18 1.19-.786V20.63a2.9 2.9 0 0 1-1.078.224c-1.483 0-2.359-.808-2.987-2.313-.247-.607-.517-.966-1.034-1.033-.27-.023-.359-.135-.359-.27 0-.27.45-.471.898-.471.652 0 1.213.404 1.797 1.235.45.651.921.943 1.483.943.561 0 .92-.202 1.437-.719.382-.381.674-.718.944-.943" />
    </svg>
  )
}
