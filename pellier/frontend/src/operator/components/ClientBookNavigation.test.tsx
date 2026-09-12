import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ClientBookNavigation from './ClientBookNavigation'
import ClientBook from '../surfaces/ClientBook'
import { ClientBookContext, useClientBookResource } from '../hooks/useClientBook'

const book = {
  total: 3, byMembership: { registered: 1, circle: 1, maison: 1 },
  clients: [
    { customerId: 'CUST-MARCO', name: 'Marco', slug: 'marco', membership: 'circle', note: 'Natural fibers.', spend12mo: 3180, orderCount: 7, personaId: 'marco' },
    { customerId: 'CUST-AMARA', name: 'Amara', slug: 'amara', membership: 'maison', note: 'Investment pieces.', spend12mo: 18900, orderCount: 5, personaId: null },
    { customerId: 'CUST-NEW', name: 'Nadia', slug: 'new', membership: 'registered', note: '', spend12mo: 410, orderCount: 1, personaId: null },
  ],
}

function Desk() {
  const resource = useClientBookResource()
  const location = useLocation()
  const navigate = useNavigate()
  return <ClientBookContext.Provider value={resource}>
    <ClientBookNavigation />
    <output data-testid="book-location">{location.pathname}{location.search}</output>
    <button type="button" onClick={() => navigate(-1)}>Browser back</button>
    <ClientBook intent={location.pathname === '/operator/chat' ? 'chat' : 'record'} />
  </ClientBookContext.Provider>
}

beforeEach(() => { sessionStorage.removeItem('pellier-operator-book-view') })
afterEach(() => { vi.unstubAllGlobals() })

describe('client book tier navigation', () => {
  it('shares the authenticated book read and synchronizes sidebar, filters, and browser history', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => book })
    vi.stubGlobal('fetch', fetch)
    render(<MemoryRouter initialEntries={['/operator?membership=maison']}>
      <Routes><Route path="/operator" element={<Desk />} /></Routes>
    </MemoryRouter>)
    await screen.findByTestId('operator-client-amara')
    expect(screen.queryByTestId('operator-client-marco')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Maison 1' })).toHaveAttribute('aria-current', 'page')
    expect(fetch).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('link', { name: 'Circle 1' }))
    expect(screen.getByTestId('book-location')).toHaveTextContent('membership=circle')
    expect(screen.getByTestId('operator-client-marco')).toBeInTheDocument()
    expect(screen.queryByTestId('operator-client-amara')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Browser back' }))
    await waitFor(() => expect(screen.getByTestId('operator-client-amara')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Maison 1' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: 'Client book 3' }))
    expect(screen.getByTestId('operator-client-marco')).toBeInTheDocument()
    expect(screen.getByTestId('operator-client-amara')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('does not present zero clients when access is denied', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 401, json: async () => ({ detail: 'authentication_required' }),
    }))
    render(<MemoryRouter><ClientBookNavigation /></MemoryRouter>)
    await screen.findByText('Counts available after operator sign-in.')
    expect(screen.getByRole('link', { name: 'Maison' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Maison 0/ })).not.toBeInTheDocument()
  })

  it('keeps chat selection scoped to the chosen client while filtering tiers', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => book })
    vi.stubGlobal('fetch', fetch)
    render(<MemoryRouter initialEntries={['/operator/chat?membership=all']}>
      <Routes><Route path="/operator/chat" element={<Desk />} /></Routes>
    </MemoryRouter>)
    await screen.findByRole('heading', { name: 'Operator chat' })
    expect(screen.getByTestId('operator-client-marco')).toHaveAttribute(
      'href', '/operator/clients/CUST-MARCO#operator-concierge',
    )
    fireEvent.click(screen.getByRole('link', { name: 'Maison 1' }))
    expect(screen.getByTestId('book-location')).toHaveTextContent('/operator/chat?membership=maison')
    expect(screen.getByTestId('operator-client-amara')).toHaveAttribute(
      'href', '/operator/clients/CUST-AMARA#operator-concierge',
    )
    expect(screen.queryByTestId('operator-client-marco')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
