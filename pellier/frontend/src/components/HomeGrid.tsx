/**
 * HomeGrid: the home page's collection, twelve pieces a page, through the
 * whole catalog.
 *
 * Page 1 is the edit: "This week at Pellier" signed out, the shopper's own
 * edit signed in. Pages 2 onward are "More from Pellier": every other piece
 * once, by department, highest rated first. Aurora orders and counts every
 * page (`GET /api/products?persona=&page=&page_size=12`, one read per page);
 * the browser never orders, slices or tops up the catalog. A stale row is
 * worse than a visible unavailable state in a workshop about grounding, so a
 * page that fails says so.
 *
 * The page number lives in the URL (`?page=3`), so Back from a piece returns
 * to the same page and position. Following a page link scrolls to the top of
 * the grid, not of the page, and moves focus to its heading. A new shopper
 * starts on page 1.
 */
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import CatalogPager, { withPage } from './CatalogPager'
import ProductCard from './ProductCard'
import { HOME_GRID, SHOPPER } from '../copy'
import { useAuth } from '../contexts/AuthContext'
import { usePersona } from '../contexts/PersonaContext'
import { apiFetch } from '../services/apiBase'
import type { PellierProduct } from '../services/types'
import '../styles/search-results.css'

/** Twelve fills complete rows at two, three, four or six cards across. */
export const HOME_PAGE_SIZE = 12

/** One page of the catalog, as `GET /api/products?page=` returns it. */
export interface CatalogPage {
  products: PellierProduct[]
  page: number
  pageSize: number
  total: number
  pages: number
}

type Load =
  | { status: 'loading' }
  | { status: 'failed' }
  | { status: 'ready'; data: CatalogPage }

/** `?page=3` as a number; anything else is page 1. */
export function pageFrom(params: URLSearchParams): number {
  const raw = params.get('page') ?? ''
  return /^[1-9]\d{0,3}$/.test(raw) ? Number(raw) : 1
}

function isCatalogPage(body: unknown): body is CatalogPage {
  const page = body as CatalogPage | null
  return Boolean(page) && Array.isArray(page?.products)
    && [page?.page, page?.pageSize, page?.total, page?.pages].every(value => typeof value === 'number')
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function Skeleton() {
  return (
    <div className="pellier-product-grid" data-testid="home-grid-skeleton" aria-hidden="true">
      {Array.from({ length: HOME_PAGE_SIZE }, (_, index) => (
        <div key={index} className="results-skeleton-card">
          <span className="results-skeleton-photo" />
          <span className="results-skeleton-line" />
          <span className="results-skeleton-line results-skeleton-line-short" />
        </div>
      ))}
    </div>
  )
}

/** The page's pieces as a range of the whole catalog: "13–24 of 100". */
function rangeOf({ page, pageSize, products, total }: CatalogPage): string {
  const first = (page - 1) * pageSize + 1
  return HOME_GRID.range(first, first + products.length - 1, total)
}

interface Extent {
  total: number
  pages: number
}

/**
 * Reads one page whenever the edit, the page or the retry count changes. The
 * catalog's size stays from the last page read, so the count and the pager
 * hold still while the next page loads.
 */
function useCatalogPage(
  edit: string,
  page: number,
  revision: number,
  onPastTheEnd: () => void,
): { load: Load; extent: Extent | null } {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [extent, setExtent] = useState<Extent | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    setLoad({ status: 'loading' })
    const query = `persona=${encodeURIComponent(edit)}&page=${page}&page_size=${HOME_PAGE_SIZE}`
    apiFetch(`/api/products?${query}`, { credentials: 'include', signal: controller.signal })
      .then(async response => {
        // A page the catalog no longer reaches (an old link): start again at page 1.
        if (page > 1 && (response.status === 404 || response.status === 422)) {
          onPastTheEnd()
          return
        }
        if (!response.ok) throw new Error(`Catalog page request failed: ${response.status}`)
        const body: unknown = await response.json()
        if (!isCatalogPage(body)) throw new Error('Catalog page returned an invalid payload.')
        setLoad({ status: 'ready', data: body })
        setExtent({ total: body.total, pages: body.pages })
      })
      .catch((error: unknown) => {
        if ((error as { name?: string })?.name === 'AbortError') return
        setLoad({ status: 'failed' })
      })
    return () => controller.abort()
  }, [edit, page, revision])
  return { load, extent }
}

export default function HomeGrid() {
  const { prefsVersion } = useAuth()
  const { persona } = usePersona()
  const [params, setParams] = useSearchParams()
  const page = pageFrom(params)
  // The persona names its own catalog grouping; signed out is the neutral edit.
  const edit = persona?.edit ?? 'fresh'
  const signedIn = Boolean(persona && persona.id !== 'fresh')
  const [revision, setRevision] = useState(0)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const headingRef = useRef<HTMLHeadingElement | null>(null)
  const followed = useRef<number | null>(null)
  const shownEdit = useRef(edit)

  const toFirstPage = () => setParams(current => withPage(current, 1), { replace: true })
  const { load, extent } = useCatalogPage(edit, page, revision, toFirstPage)

  // A new shopper starts on page 1 of their own edit.
  useEffect(() => {
    if (shownEdit.current === edit) return
    shownEdit.current = edit
    if (params.has('page')) toFirstPage()
  }, [edit])

  // A followed page link lands at the top of the grid, with focus on its heading.
  useEffect(() => {
    if (followed.current !== page) return
    followed.current = null
    shellRef.current?.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'instant' : 'smooth' })
    headingRef.current?.focus({ preventScroll: true })
  }, [page])

  const title = page > 1
    ? HOME_GRID.MORE
    : signedIn && persona ? SHOPPER.edit(persona.display_name.split(' ')[0]) : HOME_GRID.TITLE
  const ready = load.status === 'ready' ? load.data : null

  return (
    <div ref={shellRef} className="pellier-edit-shell pellier-home-grid pb-16 md:pb-20" data-testid="home-collection">
      <div className="pellier-gridhead">
        <h2 ref={headingRef} tabIndex={-1} data-testid="home-grid-title" className="pellier-statement">
          {title}
        </h2>
        {extent ? (
          <p className="pellier-gridhead-meta">
            <span data-testid="home-grid-count">{HOME_GRID.pieces(extent.total)}</span>
            {ready && ready.products.length > 0 ? (
              <span className="pellier-gridhead-range" data-testid="home-grid-range">{rangeOf(ready)}</span>
            ) : null}
          </p>
        ) : null}
      </div>

      {load.status === 'loading' ? (
        <>
          <Skeleton />
          <span className="gov-visually-hidden" role="status">{HOME_GRID.LOADING}</span>
        </>
      ) : null}

      {load.status === 'failed' ? (
        <div className="mx-auto max-w-[760px] py-16 text-center">
          <p className="pellier-eyebrow">{HOME_GRID.UNAVAILABLE_EYEBROW}</p>
          <p className="pellier-statement mt-3" style={{ fontSize: 'var(--text-section)' }}>
            {HOME_GRID.UNAVAILABLE_TITLE}
          </p>
          <p className="mt-4 font-sans text-[14px] text-ink-2" role="alert">{HOME_GRID.UNAVAILABLE_BODY}</p>
          <button type="button" className="pellier-retry mt-5" onClick={() => setRevision(v => v + 1)}>
            {HOME_GRID.RELOAD}
          </button>
        </div>
      ) : null}

      {ready && ready.products.length === 0 ? (
        <div className="mx-auto max-w-[760px] py-16 text-center">
          <p className="pellier-eyebrow">{HOME_GRID.EMPTY_EYEBROW}</p>
          <p className="mt-4 font-sans text-[14px] text-ink-2">{HOME_GRID.EMPTY_BODY}</p>
        </div>
      ) : null}

      {ready && ready.products.length > 0 ? (
        <div key={`${prefsVersion}-${edit}`} className="pellier-product-grid" data-testid="home-grid">
          {ready.products.map((product, index) => (
            <ProductCard key={product.id} product={product} index={index % 3} />
          ))}
        </div>
      ) : null}

      {extent && load.status !== 'failed' ? (
        <CatalogPager page={page} pages={extent.pages} onNavigate={target => { followed.current = target }} />
      ) : null}
    </div>
  )
}
