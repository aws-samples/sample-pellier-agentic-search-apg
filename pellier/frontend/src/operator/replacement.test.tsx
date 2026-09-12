import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OperatorClientRecord, OperatorReplacement } from '../services/operator'

const api = vi.hoisted(() => ({ read: vi.fn(), prepare: vi.fn() }))
vi.mock('../services/operator', async original => ({
  ...await original<typeof import('../services/operator')>(),
  fetchReplacements: api.read,
  prepareReplacement: api.prepare,
}))
import ReplacementCare from './components/ReplacementCare'
import ReplacementEvidence from '../observatory/surfaces/observe/ReplacementEvidence'

const replacement: OperatorReplacement = {
  replacementId: '2e8e1191-caa8-4f88-a9cc-186c9572276c', reviewId: 91,
  orderId: 7, productId: '37', productName: 'Wabi-Sabi Bowl', quantity: 1,
  disposition: 'inspection_required', state: 'outcome_unknown',
  providerOperationId: null, executionArn: null, provider: 'workshop-simulator',
  idempotencyKey: 'approved-operation-key', approvalHash: 'a'.repeat(64),
  outbox: { eventId: 'event-7', attempts: 2, publishedAt: null },
  createdAt: '2026-09-12T10:00:00Z', updatedAt: '2026-09-12T10:01:00Z',
  events: [{ type: 'reserved', at: '2026-09-12T10:00:00Z', details: {} }],
}
const record = {
  client: { customerId: 'CUST-THEO' },
  orders: [{ orderId: 7, productId: '37', productName: 'Wabi-Sabi Bowl', quantity: 1 }],
} as OperatorClientRecord

beforeEach(() => {
  api.read.mockReset().mockResolvedValue({ available: true, replacements: [replacement] })
  api.prepare.mockReset().mockResolvedValue({ reviewId: 91 })
})

describe('Replacement care', () => {
  function open() {
    return render(<MemoryRouter><Routes>
      <Route path="/" element={<ReplacementCare record={record} />} />
      <Route path="/operator/reviews/:reviewId" element={<p>Prepared review</p>} />
    </Routes></MemoryRouter>)
  }
  it('reads the client scope without preparing or executing on mount', async () => {
    open()
    expect(await screen.findByText('Outcome needs checking')).toBeInTheDocument()
    expect(api.read).toHaveBeenCalledWith('CUST-THEO')
    expect(api.prepare).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Inspect recovery evidence' })).toHaveAttribute(
      'href', `/observatory/replacement?customer=CUST-THEO&replacement=${replacement.replacementId}`,
    )
    expect(screen.getByText(/does not describe a real shipment/)).toBeInTheDocument()
  })

  it('prepares only the selected order and report, then opens human review', async () => {
    open()
    await screen.findByText('Outcome needs checking')
    fireEvent.click(screen.getByText('Prepare a damaged-item replacement'))
    fireEvent.change(screen.getByLabelText('What did the client report?'), { target: { value: 'Chipped rim reported' } })
    fireEvent.click(screen.getByRole('button', { name: 'Prepare for review' }))
    await screen.findByText('Prepared review')
    expect(api.prepare).toHaveBeenCalledWith('CUST-THEO', 7, 1, 'Chipped rim reported')
  })

  it('offers no preparation when the capability is unavailable', async () => {
    api.read.mockResolvedValue({ available: false, replacements: [] })
    open()
    await screen.findByText('Replacement care is not enabled in this deployment.')
    expect(screen.queryByRole('button', { name: 'Prepare for review' })).not.toBeInTheDocument()
  })

  it('does not present stale evidence after a failed refresh', async () => {
    open()
    await screen.findByText('Outcome needs checking')
    api.read.mockRejectedValue(new Error('unavailable'))
    fireEvent.click(screen.getByRole('button', { name: 'Check outcome' }))
    await screen.findByText(/latest replacement record is unavailable/)
    expect(screen.queryByText('Outcome needs checking')).not.toBeInTheDocument()
  })
})

describe('Replacement Observatory evidence', () => {
  function open(query = `?customer=CUST-THEO&replacement=${replacement.replacementId}`) {
    return render(<MemoryRouter initialEntries={[`/observatory/replacement${query}`]}><ReplacementEvidence /></MemoryRouter>)
  }
  it('requests one exact operation and labels its provider boundary', async () => {
    open()
    await screen.findByText('Wabi-Sabi Bowl')
    expect(api.read).toHaveBeenCalledWith('CUST-THEO', replacement.replacementId)
    expect(screen.getByText(/not a real carrier shipment/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Inspect human decision and policy' })).toHaveAttribute('href', '/operator/reviews/91')
    expect(screen.getByText(/2 delivery attempts/)).toBeInTheDocument()
  })

  it('does not substitute a different operation for the selected one', async () => {
    open('?customer=CUST-THEO&replacement=missing')
    await screen.findByText(/No other operation has been substituted/)
    expect(screen.queryByText('Wabi-Sabi Bowl')).not.toBeInTheDocument()
  })

  it('does not fetch a record without a complete selection', async () => {
    open('')
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Open this view from Replacement care'))
    expect(api.read).not.toHaveBeenCalled()
  })
})
