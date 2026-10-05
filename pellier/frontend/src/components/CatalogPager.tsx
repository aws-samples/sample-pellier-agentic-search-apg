/**
 * CatalogPager: Previous, the page numbers and Next, under the home grid.
 *
 * Every control is a link to its page (`?page=3`; page 1 is the bare `/`), so
 * the page lives in the URL and Back from a piece returns to it. The current
 * page carries `aria-current="page"`. On the first and last pages, Previous
 * and Next stay in place but do nothing (`aria-disabled`), so the row never
 * shifts. On a phone the numbers give way to "Page 2 of 9".
 */
import { Link, useSearchParams } from 'react-router-dom'
import { PAGER } from '../copy'

/** The URL's parameters with `page` set; page 1 drops it. Any other parameter stays. */
export function withPage(params: URLSearchParams, page: number): URLSearchParams {
  const next = new URLSearchParams(params)
  if (page <= 1) next.delete('page')
  else next.set('page', String(page))
  return next
}

function pageSearch(params: URLSearchParams, page: number): string {
  const query = withPage(params, page).toString()
  return query ? `?${query}` : ''
}

interface StepProps {
  label: string
  target: number
  enabled: boolean
  rel: 'prev' | 'next'
  params: URLSearchParams
  onNavigate: (page: number) => void
}

function Step({ label, target, enabled, rel, params, onNavigate }: StepProps) {
  if (!enabled) {
    return (
      <a role="link" aria-disabled="true" className="pellier-pager-step" data-testid={`home-pager-${rel}`}>
        {label}
      </a>
    )
  }
  return (
    <Link
      to={{ search: pageSearch(params, target) }}
      rel={rel}
      className="pellier-pager-step"
      data-testid={`home-pager-${rel}`}
      onClick={() => onNavigate(target)}
    >
      {label}
    </Link>
  )
}

interface CatalogPagerProps {
  page: number
  pages: number
  /** Called with the page a followed link leads to, before the URL changes. */
  onNavigate: (page: number) => void
}

export default function CatalogPager({ page, pages, onNavigate }: CatalogPagerProps) {
  const [params] = useSearchParams()
  if (pages <= 1) return null
  const numbers = Array.from({ length: pages }, (_, index) => index + 1)
  return (
    <nav className="pellier-pager" aria-label={PAGER.LABEL} data-testid="home-pager">
      <Step label={PAGER.PREVIOUS} target={page - 1} enabled={page > 1} rel="prev" params={params} onNavigate={onNavigate} />
      <ol className="pellier-pager-pages">
        {numbers.map(n => (
          <li key={n}>
            <Link
              to={{ search: pageSearch(params, n) }}
              className="pellier-pager-page"
              aria-label={PAGER.page(n)}
              aria-current={n === page ? 'page' : undefined}
              data-testid="home-pager-page"
              onClick={() => onNavigate(n)}
            >
              {n}
            </Link>
          </li>
        ))}
      </ol>
      <p className="pellier-pager-status" data-testid="home-pager-status">{PAGER.status(page, pages)}</p>
      <Step label={PAGER.NEXT} target={page + 1} enabled={page < pages} rel="next" params={params} onNavigate={onNavigate} />
    </nav>
  )
}
