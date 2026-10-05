/**
 * SearchResults: the storefront's results view, in the page column.
 *
 * "Results for <query>", the count of pieces in the grid, the limits the
 * search applied as tags (each marked "from earlier" when the shopper stated
 * it in an earlier message, or "added by Pellier" when the shopper never
 * stated it) and a way back to the whole store. With the Builder view on,
 * "How it ranked" sits full width above the grid; when the turn ran more
 * than one catalog call, a row of buttons picks which call's table it shows,
 * and no numbers are merged. Then the grid: a skeleton while the turn's
 * search runs, then the answer's picks, each tagged "Pellier's pick", in the
 * answer's order, followed by the rest of the result in its own order. The
 * first twelve show, so the rows are full at two, three, four or six across;
 * "Show all N pieces" shows the rest. An empty result names what the limits
 * left out.
 *
 * Everything shown comes from the turn's evidence (`StoreResultsContext`);
 * the count is the grid's own size and the cards are read for exactly
 * those ids. While a turn runs, its status line follows the same stream
 * events as the dock. A note about what a result cannot say (a managed
 * rail's receipt) is Builder evidence: it shows only with the Builder view
 * on, in the ranking panel, and the shopper sees shopper copy alone.
 */
import { useEffect, useRef, useState } from 'react'
import { RESULTS } from '../copy'
import { PAGE_RANKING_ID, useStoreResults, type RankedCall, type ShownResult } from '../contexts/StoreResultsContext'
import ProductCard from './ProductCard'
import { RankingPanel, StatusLine, StatusTag, useBuilderView, type ResultLimit, type TagTone } from './turn'
import { removalLabels } from './turn/RankingPanel'
import '../styles/search-results.css'

/** Twelve fills complete rows at two, three, four or six cards across. */
const FIRST_PIECES = 12
const SKELETON_CARDS = FIRST_PIECES

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

/**
 * The count above the grid describes the grid: the result's own size, from
 * the backend, plus any pick another of the turn's results held.
 */
function gridCount(shown: ShownResult | null): number | null {
  return typeof shown?.results.count === 'number' ? shown.ids.length : null
}

/** Builder view: one button per catalog call of the turn, when there is more than one. */
function RankedCalls({ calls, selected, onSelect }: {
  calls: RankedCall[]
  selected: RankedCall
  onSelect: (stepId: string) => void
}) {
  return (
    <div className="results-calls" role="group" aria-label={RESULTS.RANKED_CALLS} data-testid="results-calls">
      {calls.map((call, index) => (
        <button
          key={call.stepId}
          type="button"
          className="results-call"
          aria-pressed={call === selected}
          data-testid="results-call"
          onClick={() => onSelect(call.stepId)}
        >
          <span className="results-call-n">{index + 1}</span>
          {call.finding ?? RESULTS.rankedCall(index + 1)}
        </button>
      ))}
    </div>
  )
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
  const gridKey = shown ? shown.ids.join(',') : null
  const [expandedFor, setExpandedFor] = useState<string | null>(null)
  const [chosenCall, setChosenCall] = useState<string | null>(null)
  const gridRef = useRef<HTMLDivElement | null>(null)
  const calls = shown?.rankings ?? []
  // The table follows the call the grid's order came from until the shopper picks another.
  const call = calls.find(entry => entry.stepId === chosenCall)
    ?? calls.find(entry => entry.ranking === shown?.ranking)
    ?? calls[0]
    ?? null
  const ranking = call?.ranking ?? null
  const panelShown = Boolean(builderView && ranking)
  // Builder evidence: never shown with the Builder view off.
  const note = builderView ? shown?.results.note ?? null : null
  const setPageRanking = results?.setPageRanking
  const expanded = gridKey !== null && expandedFor === gridKey

  useEffect(() => {
    setPageRanking?.(panelShown ? ranking : null)
    return () => setPageRanking?.(null)
  }, [panelShown, ranking, setPageRanking])

  // A newly shown pick or result starts on its first twelve and its own table.
  useEffect(() => {
    setChosenCall(null)
  }, [gridKey])

  // "Show all" goes once pressed; the first piece it added takes the focus.
  useEffect(() => {
    if (!expanded) return
    gridRef.current?.querySelectorAll<HTMLAnchorElement>('.pellier-card-name a')[FIRST_PIECES]?.focus()
  }, [expanded])

  if (!results || view?.kind !== 'results') return null
  const { cards, status, failed, clear, retryCards } = results
  const ids = shown?.ids ?? []
  const ready = cards?.status === 'ready' ? cards.products : null
  const count = gridCount(shown)
  const limits = shown?.results.limits ?? []
  const picks = new Set(shown?.picks ?? [])
  const visible = ready && !expanded ? ready.slice(0, FIRST_PIECES) : ready
  const hidden = ready ? ready.length - (visible?.length ?? 0) : 0

  return (
    <div className="pellier-edit-shell results-shell" data-testid="results-view">
      <div className="results-head">
        <div className="pellier-gridhead results-gridhead">
          <h2 className="pellier-statement" data-testid="results-title">{RESULTS.title(view.query)}</h2>
          {count !== null ? (
            <span className="pellier-eyebrow results-count" data-testid="results-count">{RESULTS.shown(count)}</span>
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

      {panelShown && call && calls.length > 1 ? (
        <RankedCalls calls={calls} selected={call} onSelect={setChosenCall} />
      ) : null}
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
        {visible && visible.length > 0 ? (
          <div className="pellier-product-grid" data-testid="results-grid" ref={gridRef}>
            {visible.map((product, index) => (
              <ProductCard key={product.id} product={product} index={index % 3} pick={picks.has(String(product.id))} />
            ))}
          </div>
        ) : null}
        {ready && hidden > 0 ? (
          <button
            type="button"
            className="results-show-all"
            data-testid="results-show-all"
            onClick={() => setExpandedFor(gridKey)}
          >
            {RESULTS.showAll(count ?? ready.length)}
          </button>
        ) : null}
        {!shown || cards?.status === 'loading' ? (
          <span className="gov-visually-hidden" role="status">{RESULTS.LOADING}</span>
        ) : null}
      </section>
    </div>
  )
}
