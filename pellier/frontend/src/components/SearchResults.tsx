/**
 * SearchResults: the storefront's results view, in the page column.
 *
 * "Results for <query>", the count of pieces in the grid, the limits the
 * search applied as tags (each marked "from earlier" when the shopper stated
 * it in an earlier message, or "added by Pellier" when the shopper never
 * stated it) and a way back to the whole store. With the Builder view on,
 * "How it ranked" sits full width above the grid. Then the grid: a skeleton
 * while the turn's search runs, the cards in the search's own order once it
 * lands, or a plain empty state naming what the limits left out.
 *
 * Everything shown comes from the turn's evidence (`StoreResultsContext`);
 * the count is the result's own size and the cards are read for exactly
 * those ids. While a turn runs, its status line follows the same stream
 * events as the dock. A note about what a result cannot say (a managed
 * rail's receipt) is Builder evidence: it shows only with the Builder view
 * on, in the ranking panel, and the shopper sees shopper copy alone.
 */
import { useEffect } from 'react'
import { RESULTS } from '../copy'
import { PAGE_RANKING_ID, useStoreResults, type ShownResult } from '../contexts/StoreResultsContext'
import ProductCard from './ProductCard'
import { RankingPanel, StatusLine, StatusTag, useBuilderView, type ResultLimit, type TagTone } from './turn'
import { removalLabels } from './turn/RankingPanel'
import '../styles/search-results.css'

const SKELETON_CARDS = 6

const LIMIT_TONES: Record<string, TagTone> = {
  stock: 'good',
  exclusions: 'blocked',
}

// Where a limit came from, when the shopper did not state it in this message.
const ORIGIN_MARKS: Partial<Record<NonNullable<ResultLimit['origin']>, string>> = {
  carried: RESULTS.FROM_EARLIER,
  agent: RESULTS.ADDED_BY_PELLIER,
}

function LimitTag({ limit }: { limit: ResultLimit }) {
  const mark = limit.origin ? ORIGIN_MARKS[limit.origin] : undefined
  return (
    <StatusTag tone={LIMIT_TONES[limit.kind] ?? 'pending'} className="results-limit">
      <span data-testid="results-limit" data-origin={limit.origin ?? 'unknown'}>
        {limit.label}
        {mark ? (
          <span className="results-limit-origin">
            <span className="gov-visually-hidden">, </span>
            {mark}
          </span>
        ) : null}
      </span>
    </StatusTag>
  )
}

/** The count above the grid describes the grid: the result's own size, from the backend. */
function countLine(shown: ShownResult | null): string | null {
  const count = shown?.results.count
  return typeof count === 'number' ? RESULTS.shown(count) : null
}

function Skeleton() {
  return (
    <div className="pellier-product-grid" data-testid="results-skeleton" aria-hidden="true">
      {Array.from({ length: SKELETON_CARDS }, (_, index) => (
        <div key={index} className="results-skeleton-card">
          <span className="results-skeleton-photo" />
          <span className="results-skeleton-line" />
          <span className="results-skeleton-line results-skeleton-line-short" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ shown }: { shown: ShownResult }) {
  const filters = shown.results.filters
  const leftOut = filters && filters.kept === 0 ? removalLabels(filters) : []
  return (
    <div className="results-empty" data-testid="results-empty" role="status">
      <p className="results-empty-title">{RESULTS.EMPTY_TITLE}</p>
      {leftOut.length > 0 ? (
        <>
          <p>{RESULTS.emptyLeftOut(leftOut)}</p>
          <p>{RESULTS.EMPTY_HINT}</p>
        </>
      ) : (
        <p>{RESULTS.EMPTY_NO_COUNTS}</p>
      )}
    </div>
  )
}

/** A turn that failed while the page showed the store: the store is as it was, and says so. */
export function StoreFailedNotice() {
  const results = useStoreResults()
  if (!results?.failed || results.view.kind !== 'store') return null
  return (
    <div className="pellier-edit-shell results-store-notice">
      <p className="results-notice" role="status" data-testid="results-failed-store">
        {RESULTS.FAILED_STORE}
      </p>
    </div>
  )
}

export default function SearchResults() {
  const results = useStoreResults()
  const [builderView] = useBuilderView()
  const view = results?.view
  const shown = view?.kind === 'results' ? view.shown : null
  const ranking = shown?.ranking ?? null
  const panelShown = Boolean(builderView && ranking)
  // Builder evidence: never shown with the Builder view off.
  const note = builderView ? shown?.results.note ?? null : null
  const setPagePanelShown = results?.setPagePanelShown

  useEffect(() => {
    setPagePanelShown?.(panelShown)
    return () => setPagePanelShown?.(false)
  }, [panelShown, setPagePanelShown])

  if (!results || view?.kind !== 'results') return null
  const { cards, status, failed, clear, retryCards } = results
  const ids = shown?.results.product_ids ?? []
  const ready = cards?.status === 'ready' ? cards.products : null
  const count = countLine(shown)
  const limits = shown?.results.limits ?? []

  return (
    <div className="pellier-edit-shell results-shell" data-testid="results-view">
      <div className="results-head">
        <div className="pellier-gridhead results-gridhead">
          <h2 className="pellier-statement" data-testid="results-title">{RESULTS.title(view.query)}</h2>
          {count ? (
            <span className="pellier-eyebrow results-count" data-testid="results-count">{count}</span>
          ) : null}
        </div>
        {status ? <StatusLine label={status} state="working" className="results-status" /> : null}
        {failed ? (
          <p className="results-notice" role="status" data-testid="results-failed">{RESULTS.FAILED}</p>
        ) : null}
        <div className="results-limits" role="group" aria-label={RESULTS.LIMITS}>
          {limits.map(limit => (
            <LimitTag key={`${limit.kind}-${limit.value ?? limit.label}`} limit={limit} />
          ))}
          <button type="button" className="results-clear" data-testid="results-clear" onClick={clear}>
            {RESULTS.CLEAR}
          </button>
        </div>
        {note && !panelShown ? <p className="results-note" data-testid="results-note">{note}</p> : null}
      </div>

      {panelShown && ranking ? (
        <RankingPanel ranking={ranking} id={PAGE_RANKING_ID} className="results-ranking" resultsNote={note} />
      ) : null}

      <section aria-label={RESULTS.GRID} className="results-grid">
        {!shown || cards?.status === 'loading' ? <Skeleton /> : null}
        {shown && ids.length === 0 ? <EmptyState shown={shown} /> : null}
        {shown && cards?.status === 'failed' ? (
          <div className="results-empty" role="status">
            <p>{RESULTS.CARDS_FAILED}</p>
            <button type="button" className="pellier-retry" onClick={retryCards}>{RESULTS.RETRY}</button>
          </div>
        ) : null}
        {ready && ready.length > 0 ? (
          <div className="pellier-product-grid" data-testid="results-grid">
            {ready.map((product, index) => (
              <ProductCard key={product.id} product={product} index={index % 3} />
            ))}
          </div>
        ) : null}
        {!shown || cards?.status === 'loading' ? (
          <span className="gov-visually-hidden" role="status">{RESULTS.LOADING}</span>
        ) : null}
      </section>
    </div>
  )
}
