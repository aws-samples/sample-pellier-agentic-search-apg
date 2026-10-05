/**
 * SearchResults: the storefront's results view, in the page column.
 *
 * "Results for <query>", the count of pieces that fit, the limits the search
 * applied as tags (each marked "from earlier" when the shopper stated it in
 * an earlier message) and a way back to the whole store. With the Builder
 * view on, "How it ranked" sits full width above the grid. Then the grid: a
 * skeleton while the turn's search runs, the cards in the search's own order
 * once it lands, or a plain empty state naming what the limits left out.
 *
 * Everything shown comes from the turn's evidence (`StoreResultsContext`);
 * the cards are read for exactly those ids. While a turn runs, its status
 * line follows the same stream events as the dock.
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

function LimitTag({ limit }: { limit: ResultLimit }) {
  const carried = limit.origin === 'carried'
  return (
    <StatusTag tone={LIMIT_TONES[limit.kind] ?? 'pending'} className="results-limit">
      <span data-testid="results-limit" data-origin={limit.origin ?? 'unknown'}>
        {limit.label}
        {carried ? (
          <span className="results-limit-origin">
            <span className="gov-visually-hidden">, </span>
            {RESULTS.FROM_EARLIER}
          </span>
        ) : null}
      </span>
    </StatusTag>
  )
}

function countLine(shown: ShownResult | null, cardCount: number | null): string | null {
  const filters = shown?.results.filters
  if (filters) return RESULTS.fit(filters.kept, filters.of)
  return cardCount === null ? null : RESULTS.shown(cardCount)
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

export default function SearchResults() {
  const results = useStoreResults()
  const [builderView] = useBuilderView()
  const view = results?.view
  const shown = view?.kind === 'results' ? view.shown : null
  const ranking = shown?.ranking ?? null
  const panelShown = Boolean(builderView && ranking)
  const setPagePanelShown = results?.setPagePanelShown

  useEffect(() => {
    setPagePanelShown?.(panelShown)
    return () => setPagePanelShown?.(false)
  }, [panelShown, setPagePanelShown])

  if (!results || view?.kind !== 'results') return null
  const { cards, status, failed, clear, retryCards } = results
  const ids = shown?.results.product_ids ?? []
  const ready = cards?.status === 'ready' ? cards.products : null
  const count = countLine(shown, ready ? ready.length : null)
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
        {shown?.results.note ? <p className="results-note">{shown.results.note}</p> : null}
      </div>

      {panelShown && ranking ? (
        <RankingPanel ranking={ranking} id={PAGE_RANKING_ID} className="results-ranking" />
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
