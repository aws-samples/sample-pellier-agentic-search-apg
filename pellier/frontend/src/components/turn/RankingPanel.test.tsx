import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import RankingPanel from './RankingPanel'
import type { RankingPayload } from './turnTypes'

const RANKING: RankingPayload = {
  available: true,
  rail: 'in-process',
  method: 'hybrid+rerank',
  rrf_k: 60,
  rerank_pool: 15,
  arms: { full_text: 12, vector: 20, fused: 23 },
  filters: { kept: 23, of: 100, removed: { budget: 61, stock: 9, exclusions: 4, department: 0 } },
  rows: [
    { product_id: '65', name: 'Stoneware Mugs, Set of 2', fts_rank: 3, vec_rank: 1, similarity: 0.61, rrf_score: 1 / 63 + 1 / 61, rerank_score: 0.84, before: 1, after: 1 },
    { product_id: '22', name: 'Linen Napkins, Set of 4', fts_rank: 1, vec_rank: null, similarity: null, rrf_score: 1 / 61, rerank_score: 0.72, before: 4, after: 2 },
    { product_id: '27', name: 'Ceramic Bud Vase', fts_rank: null, vec_rank: 2, similarity: 0.58, rrf_score: 1 / 62, rerank_score: 0.4, before: 2, after: 3 },
  ],
}

describe('RankingPanel', () => {
  it('shows the filter counts as chips in the brief order', () => {
    render(<RankingPanel ranking={RANKING} />)
    const chips = screen.getAllByTestId('status-tag').map(chip => chip.textContent)
    expect(chips.slice(0, 6)).toEqual([
      'Kept 23 of 100', '61 over budget', '9 sold out', '4 excluded', 'Full text 12', 'Vector 20',
    ])
    expect(screen.getByText(/fused with RRF \(k=60\), then Cohere Rerank on the top 15/)).toBeInTheDocument()
  })

  it('draws each arm as 1/(k + rank) of the fused score and shows the raw similarity', () => {
    render(<RankingPanel ranking={RANKING} />)
    const rows = screen.getAllByTestId('ranking-row')
    expect(rows).toHaveLength(3)
    const first = rows[0]
    expect(first).toHaveTextContent('Stoneware Mugs, Set of 2')
    expect(first).toHaveTextContent('#3')
    expect(first).toHaveTextContent('#1 0.61')
    expect(first).toHaveTextContent('0.84')
    const ft = first.querySelector('.tn-rank-bar-ft') as HTMLElement
    const vec = first.querySelector('.tn-rank-bar-vec') as HTMLElement
    const fused = 1 / 63 + 1 / 61
    expect(parseFloat(ft.style.width)).toBeCloseTo((100 * (1 / 63)) / fused, 3)
    expect(parseFloat(vec.style.width)).toBeCloseTo((100 * (1 / 61)) / fused, 3)
    // An arm the product missed draws nothing.
    const second = rows[1]
    expect((second.querySelector('.tn-rank-bar-vec') as HTMLElement).style.width).toBe('0%')
  })

  it('tags how far rerank moved a row', () => {
    render(<RankingPanel ranking={RANKING} />)
    const rows = screen.getAllByTestId('ranking-row')
    expect(within(rows[0]).queryByTestId('status-tag')).toBeNull()
    expect(within(rows[1]).getByTestId('status-tag')).toHaveTextContent('up 2')
    expect(within(rows[1]).getByTestId('status-tag')).toHaveAttribute('data-tone', 'good')
    expect(within(rows[2]).getByTestId('status-tag')).toHaveTextContent('down 1')
    expect(within(rows[2]).getByTestId('status-tag')).toHaveAttribute('data-tone', 'blocked')
  })

  it('says plainly when the detail is unavailable on a rail', () => {
    render(<RankingPanel ranking={{ available: false, rail: 'gateway-mcp', reason: 'No retrieval receipt was written for this turn' }} />)
    expect(screen.getByTestId('ranking-panel')).toHaveTextContent('No retrieval receipt was written for this turn')
    expect(screen.queryByTestId('ranking-row')).toBeNull()
  })

  it('carries the receipt note from the managed rail', () => {
    render(<RankingPanel ranking={{ ...RANKING, filters: null, note: 'Read from the retrieval receipt: no vector similarity or filter counts on this rail' }} />)
    expect(screen.getByText(/Read from the retrieval receipt/)).toBeInTheDocument()
    expect(screen.queryByText(/Kept/)).toBeNull()
  })
})
