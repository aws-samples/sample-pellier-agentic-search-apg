/**
 * The checkpoint offers only the disputed pieces that still lack a return row.
 *
 * Jessica's ticket names two pieces. Recording the robe answers the robe; it
 * says nothing about the catchall, so the catchall is what remains to review.
 */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import ConciergeHumanCheckpoint from './ConciergeHumanCheckpoint'
import type { OperatorClientRecord } from '../../services/operator'

function record(unrecorded?: string[]): OperatorClientRecord {
  return {
    client: {
      customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura',
      membership: 'circle', spend12mo: 3940, orderCount: 2, orderValue: 432.66,
      lastOrderAt: null, note: 'Open return dispute on a catchall and a robe.',
      personaId: null,
      returnEvidence: {
        authoritativeReturnCount: unrecorded ? 2 - unrecorded.length : 0,
        supportAssertsReturn: true,
        // A return request never confirms receipt, so the claim stays unconfirmed.
        unconfirmedReturnAssertion: true,
        disputedProductIds: ['41', '42'],
        ...(unrecorded ? { unrecordedDisputedProductIds: unrecorded } : {}),
      },
    },
    orders: [
      { orderId: 406, productId: '41', productName: 'Coral Lacquer Catchall',
        brand: 'Pellier Maison', price: 325.36, quantity: 1, placedAt: null,
        imageUrl: '' },
      { orderId: 407, productId: '42', productName: 'Luxury Bath Robe, Sage',
        brand: 'NestWell', price: 107.3, quantity: 1, placedAt: null, imageUrl: '' },
    ],
    tickets: [{
      ticketId: 'TKT-2026-3015', subject: 'Return received, refund amount disputed',
      status: 'pending', channel: 'chat',
      lastNote: 'Return logged for the catchall and the robe.',
      openedAt: null, resolvedAt: null,
    }],
    credits: [],
  } as unknown as OperatorClientRecord
}

describe('ConciergeHumanCheckpoint', () => {
  it('offers both named pieces while neither has a return row', () => {
    render(<ConciergeHumanCheckpoint record={record(['41', '42'])} disabled={false} onPrepare={() => {}} />)
    expect(screen.getByText('Coral Lacquer Catchall')).toBeTruthy()
    expect(screen.getByText('Luxury Bath Robe, Sage')).toBeTruthy()
  })

  it('offers only the piece still unrecorded after one return is recorded', () => {
    render(<ConciergeHumanCheckpoint record={record(['41'])} disabled={false} onPrepare={() => {}} />)
    expect(screen.getByText('Coral Lacquer Catchall')).toBeTruthy()
    expect(screen.queryByText('Luxury Bath Robe, Sage')).toBeNull()
  })

  it('retires once every named piece has a return record, though receipt stays unverified', () => {
    render(<ConciergeHumanCheckpoint record={record([])} disabled={false} onPrepare={() => {}} />)
    expect(screen.queryByTestId('operator-concierge-human-checkpoint')).toBeNull()
  })

  it('keeps the earlier behaviour when the backend predates the per-item field', () => {
    render(<ConciergeHumanCheckpoint record={record()} disabled={false} onPrepare={() => {}} />)
    expect(screen.getByText('Luxury Bath Robe, Sage')).toBeTruthy()
  })

  it('requires the customer\'s stated reason and sends it verbatim', () => {
    const onPrepare = vi.fn()
    render(<ConciergeHumanCheckpoint record={record(['41', '42'])} disabled={false} onPrepare={onPrepare} />)
    const prepare = screen.getByRole('button', { name: 'Prepare review' }) as HTMLButtonElement
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('')
    expect(prepare.disabled).toBe(true)
    expect(screen.getAllByRole('radio').every((radio) => !(radio as HTMLInputElement).checked)).toBe(true)
    // A disabled control names why, in text a screen reader reaches.
    expect(prepare.getAttribute('aria-describedby')).toBe('operator-concierge-checkpoint-reason-note')
    expect(screen.getByText('Use the reason the customer stated. Pellier never fills it in.')).toBeTruthy()

    fireEvent.click(screen.getByLabelText(/Luxury Bath Robe, Sage/))
    fireEvent.change(select, { target: { value: 'changed_mind' } })
    expect(prepare.disabled).toBe(false)
    expect(prepare.hasAttribute('aria-describedby')).toBe(false)
    fireEvent.click(prepare)
    expect(onPrepare).toHaveBeenCalledWith(
      'Prepare the return for "Luxury Bath Robe, Sage" on order #407 for review. ' +
        "Customer's stated reason: changed_mind.",
    )
  })

  it('requires an explicit item even after the reason is supplied', () => {
    const onPrepare = vi.fn()
    render(<ConciergeHumanCheckpoint record={record(['41', '42'])} disabled={false} onPrepare={onPrepare} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'changed_mind' } })
    const prepare = screen.getByRole('button', { name: 'Prepare review' }) as HTMLButtonElement
    expect(prepare.disabled).toBe(true)
    fireEvent.click(prepare)
    expect(onPrepare).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText(/Luxury Bath Robe, Sage/))
    expect(prepare.disabled).toBe(false)
  })

  it('does not guess candidates when an assertion names no product', () => {
    const unscoped = record([])
    unscoped.tickets[0].lastNote = 'Item unspecified.'
    render(<ConciergeHumanCheckpoint record={unscoped} disabled={false} onPrepare={() => {}} />)
    expect(screen.queryByTestId('operator-concierge-human-checkpoint')).toBeNull()
  })
})
