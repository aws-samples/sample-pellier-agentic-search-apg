import { fireEvent, render, screen } from '@testing-library/react'
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

const replacement: OperatorReplacement = {
  replacementId: '2e8e1191-caa8-4f88-a9cc-186c9572276c', reviewId: 91,
  orderId: 7, productId: '37', productName: 'Wabi-Sabi Bowl', quantity: 1,
  disposition: 'inspection_required', state: 'outcome_unknown',
  workflowResolution: null,
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

  it('shows operator follow-up beside accepted fulfillment without inventing a shipment', async () => {
    api.read.mockResolvedValue({ available: true, replacements: [{
      ...replacement, state: 'accepted', workflowResolution: 'operator_review_required',
    }] })
    open()
    await screen.findByText('Operator follow-up required')
    expect(screen.getByText('Accepted by fulfillment')).toBeInTheDocument()
    expect(screen.queryByText('Shipment recorded')).not.toBeInTheDocument()
    expect(api.prepare).not.toHaveBeenCalled()
  })

  it('closes the follow-up only when the refreshed record reports its resolution', async () => {
    api.read.mockResolvedValue({ available: true, replacements: [{
      ...replacement, state: 'accepted', workflowResolution: 'operator_review_required',
    }] })
    open()
    await screen.findByText('Operator follow-up required')
    api.read.mockResolvedValue({ available: true, replacements: [{
      ...replacement, state: 'shipped', workflowResolution: 'shipment_recorded',
    }] })
    fireEvent.click(screen.getByRole('button', { name: 'Check outcome' }))
    await screen.findByText('Shipment recorded')
    expect(screen.queryByText('Operator follow-up required')).not.toBeInTheDocument()
    expect(api.prepare).not.toHaveBeenCalled()
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
