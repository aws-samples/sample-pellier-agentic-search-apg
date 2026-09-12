import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConciergeSession } from '../../../services/operator'

const fetchSession = vi.hoisted(() => vi.fn())
vi.mock('../../../services/operator', async importOriginal => ({
  ...await importOriginal<typeof import('../../../services/operator')>(),
  fetchConciergeSession: fetchSession,
}))
import OperatorTurnEvidence from './OperatorTurnEvidence'

const record: ConciergeSession = {
  sessionId: 's-7', customerId: 'CUST-THEO', surface: 'operator', createdBy: 'operator',
  truncated: false,
  messages: [
    { messageId: 1, role: 'user', content: 'Inspect this return', turnId: 't-7', turnState: 'incomplete', actorType: 'operator', createdAt: null },
    { messageId: 2, role: 'assistant', content: 'The ticket is reported context.', turnId: 't-7', turnState: 'complete', actorType: 'assistant', createdAt: null,
      artifact: {
        investigation: [{ kind: 'memory', label: 'Read prior context', source: 'AgentCore Memory', status: 'complete', durationMs: 83 }],
        evidence: [{ kind: 'ticket', source: 'Amazon Aurora', label: 'Support ticket', role: 'context', status: 'unverified', note: 'The ticket reports a return.' }],
      },
    },
    { messageId: 3, role: 'assistant', content: 'A different turn', turnId: 't-8', turnState: 'complete', actorType: 'assistant', createdAt: null },
  ],
}

function open(path = '/observatory/operator-turn?customer=CUST-THEO&session=s-7&turn=t-7') {
  return render(<MemoryRouter initialEntries={[path]}><OperatorTurnEvidence /></MemoryRouter>)
}

beforeEach(() => { fetchSession.mockReset(); fetchSession.mockResolvedValue(record) })

describe('Operator turn evidence', () => {
  it('reads the scoped persisted session and renders only the selected turn', async () => {
    open()
    expect(await screen.findByText('The ticket is reported context.')).toBeInTheDocument()
    expect(fetchSession).toHaveBeenCalledWith('CUST-THEO', 's-7')
    expect(screen.queryByText('A different turn')).not.toBeInTheDocument()
    expect(screen.getByText('Remembered context')).toBeInTheDocument()
    expect(screen.getByText('context · unverified')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to client' })).toHaveAttribute('href', '/operator/clients/CUST-THEO#operator-concierge')
  })

  it('refuses a mismatched customer record rather than presenting its evidence', async () => {
    fetchSession.mockResolvedValue({ ...record, customerId: 'CUST-ANNA' })
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('does not match')
    expect(screen.queryByText('The ticket is reported context.')).not.toBeInTheDocument()
  })

  it('does not substitute the latest answer for a missing turn', async () => {
    open('/observatory/operator-turn?customer=CUST-THEO&session=s-7&turn=absent')
    expect(await screen.findByText(/This turn is not present/)).toBeInTheDocument()
    expect(screen.queryByText('A different turn')).not.toBeInTheDocument()
  })

  it('makes no record request without a complete selection', () => {
    open('/observatory/operator-turn')
    expect(fetchSession).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Open this view from an Operator conversation')
  })
})
