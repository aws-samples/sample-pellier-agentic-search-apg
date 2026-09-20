import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { OperatorBook } from '../../services/operator'
import ClientBook from './ClientBook'

const book: OperatorBook = {
  total: 4,
  byMembership: { maison: 1, circle: 2, registered: 1 },
  clients: [
    { customerId: 'CUST-SARAH', slug: 'sarah', name: 'Sarah Chen', membership: 'maison', spend12mo: 11600, orderCount: 4, orderValue: 500, lastOrderAt: null, personaId: null, note: 'Buys for a whole room.', openCase: 'Missing delivery', openCaseStatus: 'open' },
    { customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura', membership: 'circle', spend12mo: 3940, orderCount: 5, orderValue: 500, lastOrderAt: null, personaId: null, note: 'Warm coral and sage.', openCase: 'Refund amount disputed', openCaseStatus: 'pending' },
    { customerId: 'CUST-DAVID', slug: 'david', name: 'David Kim', membership: 'circle', spend12mo: 5240, orderCount: 3, orderValue: 500, lastOrderAt: null, personaId: null, note: 'Open return mentioned in an old preferences brief.', openCase: null, openCaseStatus: null },
    { customerId: 'CUST-KEVIN', slug: 'kevin', name: 'Kevin Patel', membership: 'registered', spend12mo: 410, orderCount: 2, orderValue: 500, lastOrderAt: null, personaId: null, note: 'New joiner.', openCase: 'Old resolved request', openCaseStatus: 'resolved' },
  ],
}

beforeEach(() => {
  sessionStorage.clear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => book }))
})
afterEach(() => vi.unstubAllGlobals())

function mount(path = '/operator', intent: 'record' | 'chat' = 'record') {
  return render(<MemoryRouter initialEntries={[path]}><ClientBook intent={intent} /></MemoryRouter>)
}

describe('client service-request signals', () => {
  it('uses recorded open and pending statuses without treating prose or resolved tickets as active work', async () => {
    mount()
    const sarah = await screen.findByTestId('operator-client-sarah')
    const jessica = screen.getByTestId('operator-client-jessica')
    expect(sarah).toHaveTextContent('Open service request')
    expect(sarah).toHaveTextContent('Missing delivery')
    expect(jessica).toHaveTextContent('Pending service request')
    expect(jessica).toHaveTextContent('Refund amount disputed')
    expect(jessica).not.toHaveTextContent(/approval|awaiting human review/i)
    expect(within(screen.getByTestId('operator-client-david')).queryByText(/service request/i)).not.toBeInTheDocument()
    expect(within(screen.getByTestId('operator-client-kevin')).queryByText(/service request/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open requests 2' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('combines request status, membership and subject search; clears all three from an empty result', async () => {
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Open requests 2' }))
    expect(screen.queryByTestId('operator-client-david')).not.toBeInTheDocument()
    expect(screen.queryByTestId('operator-client-kevin')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Showing 2 of 4 · Open requests')
    fireEvent.click(screen.getByTestId('operator-ladder-circle'))
    fireEvent.change(screen.getByTestId('operator-book-search'), { target: { value: '  REFUND  ' } })
    expect(screen.getByTestId('operator-client-jessica')).toBeInTheDocument()
    expect(screen.queryByTestId('operator-client-sarah')).not.toBeInTheDocument()
    fireEvent.change(screen.getByTestId('operator-book-search'), { target: { value: 'missing delivery' } })
    expect(screen.getByText(/No clients match these filters/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all clients' }))
    expect(screen.getByTestId('operator-book-search')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Open requests 2' })).toHaveAttribute('aria-pressed', 'false')
    for (const client of book.clients) expect(screen.getByTestId(`operator-client-${client.slug}`)).toBeInTheDocument()
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })

  it('restores the request filter and typed subject after opening a record and returning with browser history', async () => {
    function Back() {
      const navigate = useNavigate()
      return <button onClick={() => navigate(-1)}>Back to clients</button>
    }
    render(<MemoryRouter initialEntries={['/operator?requests=open&membership=circle']}>
      <Routes>
        <Route path="/operator" element={<ClientBook />} />
        <Route path="/operator/clients/:id" element={<Back />} />
      </Routes>
    </MemoryRouter>)
    await screen.findByTestId('operator-client-jessica')
    fireEvent.change(screen.getByTestId('operator-book-search'), { target: { value: 'refund' } })
    fireEvent.click(screen.getByTestId('operator-client-jessica'))
    fireEvent.click(screen.getByRole('button', { name: 'Back to clients' }))
    await screen.findByTestId('operator-client-jessica')
    expect(screen.getByTestId('operator-book-search')).toHaveValue('refund')
    expect(screen.getByRole('button', { name: 'Open requests 2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByTestId('operator-client-david')).not.toBeInTheDocument()
  })

  it('keeps chat entry points intact when filtering by requests', async () => {
    mount('/operator/chat?requests=open', 'chat')
    const jessica = await screen.findByTestId('operator-client-jessica')
    expect(jessica).toHaveAttribute('href', '/operator/clients/CUST-JESSICA#operator-concierge')
    expect(jessica).toHaveTextContent('Pending service request')
    fireEvent.click(screen.getByRole('button', { name: 'Open requests 2' }))
    expect(screen.getByTestId('operator-client-david')).toBeInTheDocument()
  })
})
