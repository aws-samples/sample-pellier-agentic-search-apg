import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import StepList, { foldSummary } from './StepList'
import type { TurnStep } from './turnTypes'

const ROUTE: TurnStep = {
  id: 'route',
  label: 'Understanding your request',
  status: 'done',
  finding: 'Sent to the Shopping agent',
  tags: ['Router', 'Skills'],
  builder: {
    tool: null,
    intent: 'shopping',
    agent: 'Shopping agent',
    model_id: 'global.anthropic.claude-opus-5',
    skills: [{ name: 'the-gift-table', display_name: 'The Gift Table', path: 'skills/the-gift-table/SKILL.md', loaded: 'fixed' }],
    skill_mode: 'fixed',
  },
}

const SEARCH: TurnStep = {
  id: 'step-1',
  label: 'Searching the catalog in Aurora',
  status: 'done',
  finding: '9 under $100 and in stock, candles left out',
  tags: ['Aurora'],
  builder: {
    tool: 'search_products',
    rail: 'in-process',
    duration_ms: 184,
    audit_id: 9031,
    receipt_id: 412,
    ranking: {
      available: true,
      rrf_k: 60,
      arms: { full_text: 12, vector: 20, fused: 23 },
      filters: { kept: 23, of: 100, removed: { budget: 61, stock: 9, exclusions: 4 } },
      rows: [
        { product_id: '65', name: 'Stoneware Mugs, Set of 2', fts_rank: 2, vec_rank: 1, similarity: 0.61, rrf_score: 0.0325, rerank_score: 0.84, before: 1, after: 1, moved: 0 },
      ],
    },
  },
}

const TICKETS: TurnStep = {
  id: 'step-2',
  label: 'Reading your tickets',
  status: 'done',
  finding: '1 open ticket, 1 closed',
  tags: ['Aurora', 'Identity'],
  builder: {
    tool: 'get_tickets',
    rail: 'in-process',
    audit_id: 9032,
    identity: { binding: 'overwritten', requested_customer: 'CUST-JESSICA', bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' },
  },
}

const RUNNING: TurnStep = { id: 'step-3', label: 'Checking stock in three warehouses', status: 'running', tags: ['Aurora'] }

describe('StepList', () => {
  it('shows each step with its finding and keeps tool names and ids out of the shopper view', () => {
    render(<StepList steps={[ROUTE, SEARCH, RUNNING]} live builderView={false} />)
    const list = screen.getByTestId('turn-steps')
    expect(within(list).getAllByTestId('turn-step')).toHaveLength(3)
    expect(screen.getByText('9 under $100 and in stock, candles left out')).toBeInTheDocument()
    expect(screen.getByText('in progress')).toBeInTheDocument()
    expect(list.textContent).not.toContain('search_products')
    expect(list.textContent).not.toContain('CUST-')
    expect(screen.queryByTestId('layer-tag')).toBeNull()
    expect(screen.queryByTestId('ranking-panel')).toBeNull()
  })

  it('folds to one line after the answer and expands on request', async () => {
    const user = userEvent.setup()
    render(<StepList steps={[ROUTE, SEARCH, TICKETS]} live={false} builderView={false} folded />)
    const fold = screen.getByTestId('turn-fold')
    expect(fold).toHaveTextContent('How Pellier answered, 3 steps')
    expect(fold).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('turn-steps')).toBeNull()
    await user.click(fold)
    expect(fold).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('turn-steps')).toBeInTheDocument()
    expect(foldSummary(1)).toBe('How Pellier answered, 1 step')
  })

  it('adds layer tags, the evidence line and the ranking panel with the Builder view on', () => {
    render(<StepList steps={[ROUTE, SEARCH]} live={false} builderView />)
    const tags = screen.getAllByTestId('layer-tag').map(tag => tag.textContent)
    expect(tags).toEqual(['Router', 'Skills', 'Aurora'])
    const evidence = screen.getAllByTestId('turn-evidence').map(line => line.textContent)
    expect(evidence[0]).toContain('intent shopping')
    expect(evidence[0]).toContain('skills the-gift-table (fixed)')
    expect(evidence[1]).toContain('audit row 9031')
    expect(evidence[1]).toContain('receipt 412')
    expect(screen.getByTestId('ranking-panel')).toBeInTheDocument()
  })

  it('renders the identity binding from structured fields, never from prose', () => {
    render(<StepList steps={[TICKETS]} live={false} builderView />)
    expect(screen.getByTestId('turn-evidence')).toHaveTextContent(
      'model asked for CUST-JESSICA, server bound CUST-THEO (overwritten); audit row 9032; rail in-process',
    )
  })

  it('marks a failed step without a check', () => {
    render(<StepList steps={[{ ...RUNNING, status: 'failed', finding: 'The stock check did not complete' }]} live={false} builderView={false} />)
    expect(screen.getByText('did not complete')).toBeInTheDocument()
    expect(screen.getByText('The stock check did not complete')).toBeInTheDocument()
  })
})
