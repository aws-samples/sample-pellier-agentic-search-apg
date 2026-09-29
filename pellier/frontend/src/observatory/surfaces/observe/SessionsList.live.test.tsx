import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { Session } from '../../types'

const { dataRequests } = vi.hoisted(() => ({
  dataRequests: [] as Array<{ key: string; params?: Record<string, string> }>,
}))

vi.mock('../../hooks/useObservatoryData', () => ({
  useObservatoryData: (options: { key: string; params?: Record<string, string> }) => {
    dataRequests.push(options)
    return {
      data: [
        {
          id: 'aurora-session-7',
          personaId: 'anna',
          openingQuery: 'Durable live Aurora session',
          elapsedMs: 4200,
          agentCount: 2,
          routingPattern: 'Storefront Dispatcher',
          timestamp: '2026-08-30T12:00:00.000Z',
          status: 'complete',
        },
        ...Array.from({ length: 9 }, (_, index) => ({
          id: `aurora-session-anna-${index + 1}`,
          personaId: 'anna',
          openingQuery: `Anna durable session ${index + 1}`,
          elapsedMs: 1800 + index,
          agentCount: 2,
          routingPattern: 'Storefront Dispatcher',
          timestamp: new Date(
            Date.parse('2026-08-30T12:01:00.000Z') + index * 60_000,
          ).toISOString(),
          status: 'complete' as const,
        })),
        {
          id: 'aurora-session-8',
          personaId: 'marco',
          openingQuery: 'A different live Aurora session',
          elapsedMs: 1300,
          agentCount: 1,
          routingPattern: 'Managed Gateway',
          timestamp: '2026-08-30T13:00:00.000Z',
          status: 'complete',
        },
        {
          id: 'grant-probe-1',
          personaId: 'anonymous',
          openingQuery: 'grant_probe',
          elapsedMs: 0,
          agentCount: 1,
          routingPattern: 'Storefront Dispatcher',
          timestamp: '2026-08-30T14:00:00.000Z',
          status: 'unknown',
          provenance: 'direct',
        },
      ] satisfies Session[],
      loading: false,
      error: null,
      refetch: vi.fn(),
    }
  },
}))

vi.mock('../../../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona: {
      id: 'anna',
      display_name: 'Anna',
    },
  }),
}))

import SessionsList from './SessionsList'

describe('SessionsList live data boundary', () => {
  it('narrows recorded sessions by the typed query', () => {
    render(
      <MemoryRouter>
        <SessionsList />
      </MemoryRouter>,
    )
    expect(screen.getByText('Anna durable session 9')).toBeInTheDocument()
    expect(screen.queryByText('Durable live Aurora session')).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId('observatory-sessions-search'), {
      target: { value: 'durable live' },
    })

    expect(screen.getByText('Durable live Aurora session')).toBeInTheDocument()
    expect(screen.queryByText('Anna durable session 1')).not.toBeInTheDocument()
  })

  it('shows the signed-in shopper only durable Aurora sessions, not canned turns', () => {
    render(
      <MemoryRouter>
        <SessionsList />
      </MemoryRouter>,
    )

    expect(screen.getByText('Anna durable session 9')).toBeInTheDocument()
    expect(screen.queryByText('A different live Aurora session')).not.toBeInTheDocument()
    expect(
      screen.queryByText('What linen do you have for 10 days in Goa?'),
    ).not.toBeInTheDocument()
  })

  it('bounds the initial session history and reveals the next page on request', () => {
    render(
      <MemoryRouter>
        <SessionsList />
      </MemoryRouter>,
    )

    expect(screen.getByText('Showing 8 of 10 recorded sessions')).toBeInTheDocument()
    expect(screen.queryByText('Durable live Aurora session')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('sessions-load-more'))

    expect(screen.getByText('Showing 10 of 10 recorded sessions')).toBeInTheDocument()
    expect(screen.getByText('Durable live Aurora session')).toBeInTheDocument()
    expect(screen.queryByTestId('sessions-load-more')).not.toBeInTheDocument()
  })

  it('asks for conversations only until direct runs are explicitly included', () => {
    dataRequests.length = 0
    render(
      <MemoryRouter initialEntries={['/observatory/sessions']}>
        <SessionsList />
      </MemoryRouter>,
    )
    expect(dataRequests.at(-1)).toEqual({ key: 'sessions', params: undefined })
    const include = screen.getByTestId('observatory-sessions-direct')
    expect(include).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(include)

    expect(include).toHaveAttribute('aria-pressed', 'true')
    expect(dataRequests.at(-1)).toEqual({ key: 'sessions', params: { include_direct: 'true' } })
    fireEvent.click(screen.getByRole('button', { name: 'View all personas' }))
    expect(screen.getByText(/Including runs outside a conversation/)).toBeInTheDocument()
    expect(screen.getByText('Outside a conversation')).toBeInTheDocument()
  })

  it('keeps the choice in the address so a shared link shows the same list', () => {
    dataRequests.length = 0
    render(
      <MemoryRouter initialEntries={['/observatory/sessions?direct=1']}>
        <SessionsList />
      </MemoryRouter>,
    )
    expect(dataRequests.at(-1)).toEqual({ key: 'sessions', params: { include_direct: 'true' } })
    expect(screen.getByTestId('observatory-sessions-direct')).toHaveAttribute('aria-pressed', 'true')
  })

  it('describes the cross-persona record as shared workshop evidence', () => {
    render(
      <MemoryRouter>
        <SessionsList />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'View all personas' }))

    expect(screen.getByText('Workshop sessions')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Every durable recorded conversation captured during the workshop is available here. Select a session to inspect its message history and tool ledger.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Instructor view/i)).not.toBeInTheDocument()
  })
})
