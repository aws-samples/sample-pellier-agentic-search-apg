import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import RankingPanel, { RankingSummary } from './RankingPanel'
import type { RankingPayload } from './turnTypes'

const RANKING: RankingPayload = {
  available: true,
  rail: 'in-process',
  method: 'hybrid+rerank',
  rrf_k: 60,
  rerank_pool: 15,
  arms: { full_text: 12, vector: 20, fused: 23 },
  filters: {
    kept: 23,
    of: 100,
    removed: { budget: 61, stock: 9, exclusions: 7, department: 0 },
    excluded: [
      { value: 'candle', count: 4, noun: 'candles' },
      { value: 'watch', count: 3, noun: 'watches' },
    ],
  },
  rows: [
    { product_id: '65', name: 'Stoneware Mugs, Set of 2', fts_rank: 3, vec_rank: 1, similarity: 0.61, rrf_score: 1 / 63 + 1 / 61, rerank_score: 0.84, before: 1, after: 1 },
    { product_id: '22', name: 'Linen Napkins, Set of 4', fts_rank: 1, vec_rank: null, similarity: null, rrf_score: 1 / 61, rerank_score: 0.72, before: 4, after: 2 },
    { product_id: '27', name: 'Ceramic Bud Vase', fts_rank: null, vec_rank: 2, similarity: 0.58, rrf_score: 1 / 62, rerank_score: null, before: 2, after: 3 },
  ],
}

describe('RankingPanel', () => {
  it('matches the prototype head: title, legend and method line', () => {
    render(<RankingPanel ranking={RANKING} />)
    const panel = screen.getByTestId('ranking-panel')
    expect(within(panel).getByText('How it ranked')).toBeInTheDocument()
    expect(panel).toHaveTextContent('Full text')
    expect(panel).toHaveTextContent('Vector')
    expect(within(panel).getByText('fused with RRF (k=60), then Cohere Rerank 3.5 on the top 15')).toBeInTheDocument()
  })

  it('shows kept, each removal by its own word, then each arm', () => {
    render(<RankingPanel ranking={RANKING} />)
    const chips = screen.getAllByTestId('status-tag').map(chip => chip.textContent)
    expect(chips.slice(0, 7)).toEqual([
      'Kept 23 of 100', '61 over budget', '9 sold out', '4 candles', '3 watches', 'Full text 12', 'Vector 20',
    ])
  })

  it('says how the order was made when rerank did not run', () => {
    render(<RankingPanel ranking={{ ...RANKING, method: 'hybrid (rerank fallback to RRF order)' }} />)
    expect(screen.getByText('fused with RRF (k=60); rerank was unavailable, so this is RRF order')).toBeInTheDocument()
    expect(screen.queryByText(/Cohere Rerank 3.5/)).toBeNull()
  })

  it('draws each arm as 1/(k + rank), sized to the fused score, and prints the payload score', () => {
    render(<RankingPanel ranking={RANKING} />)
    const rows = screen.getAllByTestId('ranking-row')
    expect(rows).toHaveLength(3)
    const first = rows[0]
    expect(first).toHaveTextContent('Stoneware Mugs, Set of 2')
    expect(first).toHaveTextContent('#3')
    expect(first.textContent).toContain('#1  0.61')
    expect(first).toHaveTextContent((1 / 63 + 1 / 61).toFixed(4))
    expect(first).toHaveTextContent('0.84')
    const ft = first.querySelector('.tn-rank-bar-ft') as HTMLElement
    const vec = first.querySelector('.tn-rank-bar-vec') as HTMLElement
    const fused = 1 / 63 + 1 / 61
    expect(parseFloat(ft.style.width)).toBeCloseTo((100 * (1 / 63)) / fused, 3)
    expect(parseFloat(vec.style.width)).toBeCloseTo((100 * (1 / 61)) / fused, 3)
    // An arm the product missed draws nothing and shows an en dash, never an em dash.
    const second = rows[1]
    expect((second.querySelector('.tn-rank-bar-vec') as HTMLElement).style.width).toBe('0%')
    expect(second.textContent).toContain('–')
    expect(rows[2].textContent).not.toContain('—')
  })

  it('never computes a fused score the payload did not send', () => {
    const missing = { ...RANKING, rows: [{ ...RANKING.rows![0], rrf_score: null }] }
    render(<RankingPanel ranking={missing} />)
    const cells = screen.getByTestId('ranking-row').querySelectorAll('.tn-rank-barcell .tn-rank-num')
    expect(cells[0].textContent).toBe('–')
  })

  it('tags how far rerank moved a row, up in green and down in red', () => {
    render(<RankingPanel ranking={RANKING} />)
    const rows = screen.getAllByTestId('ranking-row')
    expect(within(rows[0]).queryByTestId('status-tag')).toBeNull()
    const up = within(rows[1]).getByTestId('status-tag')
    expect(up).toHaveTextContent('↑2')
    expect(up).toHaveTextContent('up 2')
    expect(up).toHaveAttribute('data-tone', 'good')
    const down = within(rows[2]).getByTestId('status-tag')
    expect(down).toHaveTextContent('↓1')
    expect(down).toHaveAttribute('data-tone', 'blocked')
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

describe('RankingSummary', () => {
  it('scrolls to the page panel when the page shows this search', () => {
    const panel = document.createElement('div')
    panel.id = 'how-it-ranked'
    panel.scrollIntoView = vi.fn()
    document.body.appendChild(panel)
    render(<RankingSummary ranking={RANKING} onPageId="how-it-ranked" />)
    const summary = screen.getByTestId('ranking-summary')
    expect(summary).toHaveTextContent('How it ranked')
    expect(summary).toHaveTextContent('Kept 23 of 100, see the table above the results')
    fireEvent.click(summary)
    expect(panel.scrollIntoView).toHaveBeenCalled()
    expect(screen.queryByTestId('ranking-panel')).toBeNull()
    panel.remove()
  })

  it('opens the panel in place when the page is not showing it', () => {
    render(<RankingSummary ranking={RANKING} onPageId={null} />)
    expect(screen.queryByTestId('ranking-panel')).toBeNull()
    fireEvent.click(screen.getByTestId('ranking-summary'))
    expect(screen.getByTestId('ranking-panel')).toBeInTheDocument()
    expect(screen.getByTestId('ranking-summary')).toHaveAttribute('aria-expanded', 'true')
  })
})
