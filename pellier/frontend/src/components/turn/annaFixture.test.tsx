/**
 * The screenshot fixture's ranking is arithmetic over its own two arms.
 *
 * `e2e/fixtures/anna-turn.ts` derives every fused position from the arms it
 * states. This recomputes RRF independently from those arms and checks each
 * row's ranks, score and `before`, the arm counts, the rerank pool, and the
 * up and down tags the panel renders from them.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RankingPanel from './RankingPanel'
import {
  ANNA_RANKING,
  ANNA_RESULT_IDS,
  FULL_TEXT_ARM,
  RERANK_POOL,
  RERANKED,
  RRF_K,
  VECTOR_ARM,
} from '../../../e2e/fixtures/anna-turn'
import { ANNA_RESULT_CARDS } from '../../../e2e/fixtures/anna-cards'

/** RRF written out again: a score per product, then a stable sort, vector rows first. */
function fusedOrder(): Array<{ id: string; score: number; fts: number | null; vec: number | null }> {
  const byId = new Map<string, { id: string; score: number; fts: number | null; vec: number | null }>()
  VECTOR_ARM.forEach(([id], index) => byId.set(id, { id, score: 1 / (RRF_K + index + 1), fts: null, vec: index + 1 }))
  FULL_TEXT_ARM.forEach(([id], index) => {
    const entry = byId.get(id) ?? { id, score: 0, fts: null, vec: null }
    entry.fts = index + 1
    entry.score += 1 / (RRF_K + index + 1)
    byId.set(id, entry)
  })
  return Array.from(byId.values()).sort((a, b) => b.score - a.score)
}

describe("Anna's fixture ranking", () => {
  const fused = fusedOrder()
  const rows = ANNA_RANKING.rows

  it('states arm counts that follow from the two arms', () => {
    const overlap = FULL_TEXT_ARM.filter(([id]) => VECTOR_ARM.some(([vid]) => vid === id)).length
    expect(ANNA_RANKING.arms).toEqual({
      full_text: FULL_TEXT_ARM.length,
      vector: VECTOR_ARM.length,
      fused: FULL_TEXT_ARM.length + VECTOR_ARM.length - overlap,
    })
    expect(fused).toHaveLength(ANNA_RANKING.arms.fused)
    expect(ANNA_RANKING.filters.kept + 31 + 1 + 4).toBe(ANNA_RANKING.filters.of)
  })

  it('gives every row the ranks, fused score and before position its arms imply', () => {
    expect(rows.map(row => row.after)).toEqual(RERANKED.map((_, index) => index + 1))
    for (const row of rows) {
      const position = fused.findIndex(entry => entry.id === row.product_id) + 1
      const entry = fused[position - 1]
      expect(position, row.name).toBeGreaterThan(0)
      expect(row.before, row.name).toBe(position)
      expect(row.fts_rank, row.name).toBe(entry.fts)
      expect(row.vec_rank, row.name).toBe(entry.vec)
      expect(row.rrf_score, row.name).toBeCloseTo(entry.score, 12)
      expect(row.before, `${row.name} must be inside the rerank pool`).toBeLessThanOrEqual(RERANK_POOL)
    }
    // A row ranked in only one arm sits below every row ranked in both.
    const lastBoth = Math.max(...fused.filter(entry => entry.fts && entry.vec).map(entry => fused.indexOf(entry)))
    const firstSingle = Math.min(...fused.filter(entry => !entry.fts || !entry.vec).map(entry => fused.indexOf(entry)))
    expect(firstSingle).toBeGreaterThan(lastBoth)
  })

  it('renders the up and down tags from those positions', () => {
    render(<RankingPanel ranking={ANNA_RANKING} />)
    const rendered = screen.getAllByTestId('ranking-row')
    expect(rendered).toHaveLength(rows.length)
    rows.forEach((row, index) => {
      const position = fused.findIndex(entry => entry.id === row.product_id) + 1
      const moved = position - row.after
      const shown = rendered[index].querySelector('.tn-rank-move [aria-hidden="true"]')?.textContent ?? null
      const spoken = rendered[index].querySelector('.tn-rank-move .gov-visually-hidden')?.textContent ?? null
      expect(shown, row.name).toBe(moved > 0 ? `\u2191${moved}` : moved < 0 ? `\u2193${-moved}` : null)
      expect(spoken, row.name).toBe(moved > 0 ? `up ${moved}` : moved < 0 ? `down ${-moved}` : null)
    })
    // The hero row: first in the vector arm only, so below the eight rows in both arms.
    expect(rendered[0].textContent).toContain('Stoneware Pour-Over Set')
    expect(rendered[0].querySelector('.tn-rank-move .gov-visually-hidden')?.textContent).toBe('up 8')
  })

  it('orders the grid as the pipeline would: reranked rows, then the pool in RRF order', () => {
    const reranked = RERANKED.map(([id]) => id)
    const rest = fused.map(entry => entry.id).filter(id => !reranked.includes(id))
    expect(ANNA_RESULT_IDS).toEqual([...reranked, ...rest].slice(0, 30))
    // The recorded cards are those ids, in that order, each in stock and under $100.
    expect(ANNA_RESULT_CARDS.map(card => String(card.id))).toEqual(ANNA_RESULT_IDS)
    for (const card of ANNA_RESULT_CARDS) {
      expect(card.price, card.name).toBeLessThanOrEqual(100)
      expect(card.quantity, card.name).toBeGreaterThan(0)
      expect(card.tags, card.name).not.toContain('candle')
    }
  })
})
