/**
 * "How it ranked": the Builder view's panel for one search.
 *
 * One component for the page and the dock. On the storefront it sits full
 * width above the results grid; the dock shows `RankingSummary`, one line
 * that scrolls to it, so the table is never shown twice. Where the page is
 * not showing that search (another route, or a later search replaced it), the
 * summary opens the same panel in place.
 *
 * The filter counts come first as chips: what the limits kept, what each
 * limit removed (an excluded value by its own word, "4 candles"), then how
 * many rows each arm returned. Then one row per product: its final position
 * and how far rerank moved it, its full-text rank, its vector rank with the
 * cosine similarity, the fused RRF score with a stacked bar of each arm's
 * 1 / (k + rank), and the rerank score. Every number is the turn's evidence;
 * the browser computes only the bar widths. An empty cell is an en dash.
 */
import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import StatusTag from './StatusTag'
import type { RankingFilters, RankingPayload, RankingRow } from './turnTypes'

export interface RankingPanelProps {
  ranking: RankingPayload
  /** The page's panel carries the id the dock's summary scrolls to. */
  id?: string
  className?: string
}

const EMPTY = '–'
const RERANKED = 'hybrid+rerank'
const RERANK_FALLBACK = 'hybrid (rerank fallback to RRF order)'

const REMOVED_LABELS: Record<string, (n: number) => string> = {
  budget: n => `${n} over budget`,
  stock: n => `${n} sold out`,
  department: n => `${n} in other departments`,
}

function contribution(rank: number | null, k: number): number {
  return rank ? 1 / (k + rank) : 0
}

function number(value: number | null | undefined, digits: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : EMPTY
}

/** What each limit removed, in the brief's order; an excluded value by its own word. */
export function removalLabels(filters: RankingFilters): string[] {
  const labels: string[] = []
  for (const [reason, count] of Object.entries(filters.removed)) {
    if (count <= 0) continue
    if (reason === 'exclusions' && filters.excluded) {
      for (const value of filters.excluded) {
        if (value.count > 0) labels.push(`${value.count} ${value.noun}`)
      }
      continue
    }
    labels.push((REMOVED_LABELS[reason] ?? (n => `${n} excluded`))(count))
  }
  return labels
}

function methodLine(ranking: RankingPayload, k: number): string {
  const fused = `fused with RRF (k=${k})`
  if (ranking.method === RERANK_FALLBACK) return `${fused}; rerank was unavailable, so this is RRF order`
  if (ranking.method === RERANKED && ranking.rerank_pool) {
    return `${fused}, then Cohere Rerank 3.5 on the top ${ranking.rerank_pool}`
  }
  return fused
}

function Movement({ moved }: { moved: number }) {
  if (moved === 0) return null
  const up = moved > 0
  return (
    <StatusTag tone={up ? 'good' : 'blocked'} className="tn-rank-move">
      <span aria-hidden="true">{`${up ? '↑' : '↓'}${Math.abs(moved)}`}</span>
      <span className="gov-visually-hidden">{`${up ? 'up' : 'down'} ${Math.abs(moved)}`}</span>
    </StatusTag>
  )
}

function Row({ row, k, maxFused }: { row: RankingRow; k: number; maxFused: number }) {
  const full = contribution(row.fts_rank, k)
  const vec = contribution(row.vec_rank, k)
  const moved = row.before != null ? row.before - row.after : 0
  return (
    <div className="tn-rank-row" role="row" data-testid="ranking-row">
      <span className="tn-rank-pos" role="cell">
        {row.after}
        <Movement moved={moved} />
      </span>
      <span className="tn-rank-name" role="cell">{row.name ?? row.product_id}</span>
      <span className="tn-rank-num" role="cell">{row.fts_rank ? `#${row.fts_rank}` : EMPTY}</span>
      <span className="tn-rank-num" role="cell">
        {row.vec_rank ? `#${row.vec_rank}` : EMPTY}
        {row.vec_rank && row.similarity != null ? `  ${number(row.similarity, 2)}` : ''}
      </span>
      <span className="tn-rank-barcell" role="cell">
        <span className="tn-rank-bar" aria-hidden="true">
          <span className="tn-rank-bar-ft" style={{ width: `${(100 * full) / maxFused}%` }} />
          <span className="tn-rank-bar-vec" style={{ width: `${(100 * vec) / maxFused}%` }} />
        </span>
        <span className="tn-rank-num">{number(row.rrf_score, 4)}</span>
      </span>
      <span className="tn-rank-num" role="cell">{number(row.rerank_score, 2)}</span>
    </div>
  )
}

export default function RankingPanel({ ranking, id, className }: RankingPanelProps) {
  const classes = ['tn-rank', className ?? ''].filter(Boolean).join(' ')
  if (!ranking.available) {
    return (
      <div id={id} className={`${classes} tn-rank-unavailable`} data-testid="ranking-panel">
        <b>How it ranked</b>
        <span className="tn-rank-note">{ranking.reason ?? 'Ranking detail is unavailable on this rail'}</span>
      </div>
    )
  }
  const k = ranking.rrf_k ?? 60
  const rows = ranking.rows ?? []
  const maxFused = Math.max(
    ...rows.map(row => contribution(row.fts_rank, k) + contribution(row.vec_rank, k)),
    0.0001,
  )
  const filters = ranking.filters
  return (
    <section id={id} className={classes} data-testid="ranking-panel" aria-label="How it ranked">
      <div className="tn-rank-head">
        <b>How it ranked</b>
        <span className="tn-rank-legend">
          <span className="tn-rank-sw tn-rank-sw-ft" aria-hidden="true" />Full text
          <span className="tn-rank-sw tn-rank-sw-vec" aria-hidden="true" />Vector
          <span className="tn-rank-note tn-rank-method">{methodLine(ranking, k)}</span>
        </span>
      </div>
      <div className="tn-rank-steps">
        {filters && <StatusTag tone="pending">Kept {filters.kept} of {filters.of}</StatusTag>}
        {filters && removalLabels(filters).map(label => (
          <StatusTag key={label} tone="blocked">{label}</StatusTag>
        ))}
        {ranking.arms && <StatusTag tone="pending">Full text {ranking.arms.full_text}</StatusTag>}
        {ranking.arms && <StatusTag tone="pending">Vector {ranking.arms.vector}</StatusTag>}
      </div>
      <div className="tn-rank-scroll">
        <div className="tn-rank-table" role="table" aria-label="How each product ranked">
          <div className="tn-rank-row tn-rank-hdr" role="row">
            {['#', 'Product', 'Full text', 'Vector', 'Fused score', 'Rerank'].map(head => (
              <span key={head} role="columnheader">{head}</span>
            ))}
          </div>
          {rows.map(row => (
            <Row key={row.product_id} row={row} k={k} maxFused={maxFused} />
          ))}
        </div>
      </div>
      {ranking.note && <span className="tn-rank-note">{ranking.note}</span>}
    </section>
  )
}

export interface RankingSummaryProps {
  ranking: RankingPayload
  /** The id of the page panel showing this same search, when the page shows it. */
  onPageId?: string | null
}

/** The dock's one line: it scrolls to the page panel, or opens the panel here. */
export function RankingSummary({ ranking, onPageId }: RankingSummaryProps) {
  const [open, setOpen] = useState(false)
  const kept = ranking.available && ranking.filters
    ? `Kept ${ranking.filters.kept} of ${ranking.filters.of}`
    : null
  const where = onPageId
    ? 'see the table above the results'
    : open ? 'hide the table' : 'show the table'
  const detail = [kept, where].filter(Boolean).join(', ')
  const show = () => {
    if (!onPageId) {
      setOpen(value => !value)
      return
    }
    const panel = document.getElementById(onPageId)
    if (!panel) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    panel.scrollIntoView({ behavior: reduce ? 'instant' : 'smooth', block: 'start' })
  }
  return (
    <>
      <button
        type="button"
        className="tn-rank-summary"
        data-testid="ranking-summary"
        aria-expanded={onPageId ? undefined : open}
        onClick={show}
      >
        <b>How it ranked</b>
        <span>{detail}</span>
        <ChevronRight size={12} strokeWidth={2} className="tn-chev" aria-hidden="true" />
      </button>
      {!onPageId && open && <RankingPanel ranking={ranking} />}
    </>
  )
}
