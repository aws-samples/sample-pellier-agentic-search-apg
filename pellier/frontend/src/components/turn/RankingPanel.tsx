/**
 * "How it ranked": the Builder view's panel for one search.
 *
 * Filter counts come first as chips. Then one row per product: its full-text
 * and vector ranks, a stacked bar of each arm's RRF contribution, the fused
 * score, the vector similarity, the rerank score, and how far rerank moved it.
 * Contributions are drawn, not raw scores, because RRF uses only ranks:
 * each arm adds 1 / (k + rank).
 */
import StatusTag from './StatusTag'
import type { RankingPayload, RankingRow } from './turnTypes'

export interface RankingPanelProps {
  ranking: RankingPayload
}

const REMOVED_LABELS: Record<string, (n: number) => string> = {
  budget: n => `${n} over budget`,
  stock: n => `${n} sold out`,
  exclusions: n => `${n} excluded`,
  department: n => `${n} in other departments`,
}

function contribution(rank: number | null, k: number): number {
  return rank ? 1 / (k + rank) : 0
}

function number(value: number | null | undefined, digits: number): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '–'
}

function Row({ row, k, maxFused }: { row: RankingRow; k: number; maxFused: number }) {
  const full = contribution(row.fts_rank, k)
  const vec = contribution(row.vec_rank, k)
  const fused = full + vec
  const moved = row.before != null ? row.before - row.after : 0
  return (
    <div className="tn-rank-row" role="row" data-testid="ranking-row">
      <span className="tn-rank-pos" role="cell">
        {row.after}
        {moved !== 0 && (
          <StatusTag tone={moved > 0 ? 'good' : 'blocked'} className="tn-rank-move">
            {moved > 0 ? `up ${moved}` : `down ${Math.abs(moved)}`}
          </StatusTag>
        )}
      </span>
      <span className="tn-rank-name" role="cell">{row.name ?? row.product_id}</span>
      <span className="tn-rank-num" role="cell">{row.fts_rank ? `#${row.fts_rank}` : '–'}</span>
      <span className="tn-rank-num" role="cell">
        {row.vec_rank ? `#${row.vec_rank}` : '–'}
        {row.similarity != null && <span className="tn-rank-sim"> {number(row.similarity, 2)}</span>}
      </span>
      <span className="tn-rank-barcell" role="cell">
        <span className="tn-rank-bar" aria-hidden="true">
          <span className="tn-rank-bar-ft" style={{ width: `${(100 * full) / maxFused}%` }} />
          <span className="tn-rank-bar-vec" style={{ width: `${(100 * vec) / maxFused}%` }} />
        </span>
        <span className="tn-rank-num">{fused ? number(row.rrf_score ?? fused, 4) : '–'}</span>
      </span>
      <span className="tn-rank-num" role="cell">{number(row.rerank_score, 2)}</span>
    </div>
  )
}

export default function RankingPanel({ ranking }: RankingPanelProps) {
  if (!ranking.available) {
    return (
      <div className="tn-rank tn-rank-unavailable" data-testid="ranking-panel">
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
    <div className="tn-rank" data-testid="ranking-panel">
      <div className="tn-rank-head">
        <b>How it ranked</b>
        <span className="tn-rank-legend">
          <span className="tn-rank-sw tn-rank-sw-ft" aria-hidden="true" />Full text
          <span className="tn-rank-sw tn-rank-sw-vec" aria-hidden="true" />Vector
          <span className="tn-rank-note">
            fused with RRF (k={k})
            {ranking.rerank_pool ? `, then Cohere Rerank on the top ${ranking.rerank_pool}` : ''}
          </span>
        </span>
      </div>
      <div className="tn-rank-steps">
        {filters && (
          <StatusTag tone="pending">Kept {filters.kept} of {filters.of}</StatusTag>
        )}
        {filters &&
          Object.entries(filters.removed)
            .filter(([, count]) => count > 0)
            .map(([reason, count]) => (
              <StatusTag key={reason} tone="blocked">
                {(REMOVED_LABELS[reason] ?? (n => `${n} removed`))(count)}
              </StatusTag>
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
    </div>
  )
}
