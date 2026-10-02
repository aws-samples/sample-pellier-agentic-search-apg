import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OperatorClientPreview from './OperatorClientPreview'

const RECORD = {
  client: {
    customerId: 'CUST-JESSICA',
    slug: 'jessica',
    name: 'Jessica Nakamura',
    membership: 'circle' as const,
    spend12mo: 3940,
    orderCount: 2,
    orderValue: 432.66,
    lastOrderAt: null,
    note: 'Open return dispute on a catchall and a robe.',
    personaId: null,
    openTicketCount: 1,
    creditBalanceCents: 0,
    creditBalance: '0.00',
    returnCount: 0,
    returnEvidence: {
      authoritativeReturnCount: 0,
      supportAssertsReturn: true,
      unconfirmedReturnAssertion: true,
    },
  },
  orders: [
    {
      orderId: 1,
      productId: '41',
      productName: 'Coral Lacquer Catchall',
      brand: 'Pellier Maison',
      price: 325.36,
      quantity: 1,
      placedAt: null,
      imageUrl: '/products/catchall.png',
    },
    {
      orderId: 2,
      productId: '42',
      productName: 'Luxury Bath Robe, Sage',
      brand: 'NestWell',
      price: 107.3,
      quantity: 1,
      placedAt: null,
      imageUrl: '/products/robe.png',
    },
  ],
  tickets: [
    {
      ticketId: 'TKT-2026-3015',
      subject: 'Return received, refund amount disputed',
      status: 'pending' as const,
      channel: 'chat',
      lastNote: 'Return logged for the catchall and robe.',
      openedAt: null,
      resolvedAt: null,
    },
  ],
  credits: [],
  returns: [],
}

function mockFetch(status = 200, body: unknown = RECORD) {
  vi.stubGlobal(
    'fetch',
    vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
}

function renderPreview(onClose = vi.fn()) {
  return {
    onClose,
    ...render(
      <MemoryRouter>
        <OperatorClientPreview
          customerId="CUST-JESSICA"
          onClose={onClose}
        />
      </MemoryRouter>,
    ),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('OperatorClientPreview', () => {
  it('renders live client, order, and service context without impersonation', async () => {
    mockFetch()
    renderPreview()

    const preview = await screen.findByTestId('operator-client-preview')
    expect(preview).toHaveTextContent('Jessica Nakamura')
    expect(preview).toHaveTextContent('Silver')
    expect(preview).toHaveTextContent('Coral Lacquer Catchall')
    expect(preview).toHaveTextContent('Return received, refund amount disputed')
    expect(preview).toHaveTextContent('Read-only')
  })

  it('keeps the support assertion separate from the authoritative return count', async () => {
    mockFetch()
    renderPreview()

    const conflict = await screen.findByTestId(
      'operator-client-preview-evidence-conflict',
    )
    expect(conflict).toHaveTextContent(
      'Service context says a return was received',
    )
    expect(conflict).toHaveTextContent('returns ledger contains 0 record')
    expect(conflict).toHaveTextContent('remain separate')
  })

  it('links back to the same client and the review queue', async () => {
    mockFetch()
    renderPreview()

    expect(
      await screen.findByTestId('operator-client-preview-record'),
    ).toHaveAttribute('href', '/operator/clients/CUST-JESSICA')
    expect(screen.getByTestId('operator-client-preview-reviews')).toHaveAttribute(
      'href',
      '/operator/reviews',
    )
  })

  it('closes without changing operator or shopper identity', async () => {
    mockFetch()
    const { onClose } = renderPreview()

    fireEvent.click(await screen.findByTestId('operator-client-preview-close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('sends credentials and renders the gated state on a 401', async () => {
    mockFetch(401, { detail: 'authentication_required' })
    renderPreview()

    expect(
      await screen.findByTestId('operator-client-preview-error'),
    ).toHaveTextContent('requires an active Pellier Operator session')
    expect(fetch).toHaveBeenCalledWith(
      '/api/operator/clients/CUST-JESSICA',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(screen.queryByText('Jessica Nakamura')).not.toBeInTheDocument()
  })
})
