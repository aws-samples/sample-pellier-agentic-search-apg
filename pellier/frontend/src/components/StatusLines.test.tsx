/**
 * StatusLines: three rows, three sources.
 *
 * Scenario comes from the persona context, verified identity from the auth
 * context, and the execution path from the last completed turn's rail. None
 * of them may be inferred from another: choosing Marco is not a sign-in, and
 * a sign-in says nothing about which rail served the turn.
 */
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AgentChatMessage } from '../hooks/useAgentChat'

const mocks = vi.hoisted(() => ({
  persona: null as null | { id: string; display_name: string },
  auth: null as null | { isAuthenticated: boolean; user: { givenName?: string; email: string; username?: string; signInMethod?: 'workshop' | 'cognito' } | null },
}))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona: mocks.persona }),
}))

vi.mock('../contexts/AuthContext', () => ({
  useOptionalAuth: () => mocks.auth,
}))

import StatusLines from './StatusLines'

function row(label: string): HTMLElement {
  const term = screen.getByText(label)
  const container = term.closest('[data-status-row]')
  if (!container) throw new Error(`no row for ${label}`)
  return container as HTMLElement
}

function turn(over: Partial<AgentChatMessage>): AgentChatMessage {
  return {
    role: 'assistant',
    content: 'answer',
    timestamp: new Date('2026-09-04T09:00:00Z'),
    agentStatus: 'complete',
    ...over,
  }
}

describe('StatusLines', () => {
  beforeEach(() => {
    mocks.persona = null
    mocks.auth = null
  })

  it('names the empty state of each source without borrowing from another', () => {
    render(<StatusLines messages={[]} />)

    expect(within(row('Scenario')).getByText('None selected')).toBeInTheDocument()
    expect(within(row('Verified identity')).getByText('Not signed in')).toBeInTheDocument()
    expect(
      within(row('Execution path')).getByText('Unknown until the first turn'),
    ).toBeInTheDocument()
  })

  it('reads the scenario from the persona context alone', () => {
    mocks.persona = { id: 'marco', display_name: 'Marco Delgado' }
    render(<StatusLines messages={[]} />)

    expect(within(row('Scenario')).getByText('Marco Delgado')).toBeInTheDocument()
    expect(within(row('Verified identity')).getByText('Not signed in')).toBeInTheDocument()
  })

  it('reads the verified identity from the Cognito session alone', () => {
    mocks.auth = {
      isAuthenticated: true,
      user: { givenName: 'marco', email: 'marco@example.com' },
    }
    render(<StatusLines messages={[]} />)

    expect(within(row('Verified identity')).getByText('marco')).toBeInTheDocument()
    expect(within(row('Scenario')).getByText('None selected')).toBeInTheDocument()
  })

  it('reads the execution path from the last completed turn', () => {
    render(
      <StatusLines
        messages={[
          { role: 'user', content: 'q1', timestamp: new Date() },
          turn({
            railDecision: {
              rail: 'in-process',
              managedRequested: false,
              available: true,
              reason: null,
            },
          }),
          { role: 'user', content: 'q2', timestamp: new Date() },
          turn({
            railDecision: {
              rail: 'gateway-mcp',
              managedRequested: true,
              available: true,
              reason: null,
            },
          }),
          { role: 'user', content: 'q3', timestamp: new Date() },
          turn({ agentStatus: 'streaming', content: '' }),
        ]}
      />,
    )

    expect(within(row('Execution path')).getByText('gateway-mcp')).toBeInTheDocument()
  })
})

describe('the workshop sign-in label', () => {
  it('names the session as a demo-shopper sign-in only when the server said so', () => {
    mocks.persona = { id: 'anna', display_name: 'Anna Lindqvist' }
    mocks.auth = { isAuthenticated: true, user: { email: 'anna@pellier.example.com', username: 'anna', signInMethod: 'workshop' } }
    render(<StatusLines messages={[]} />)
    expect(row('Verified identity')).toHaveTextContent('anna, Workshop sign-in (demo shoppers)')
  })

  it('shows a plain identity for a typed or hosted sign-in', () => {
    mocks.persona = null
    mocks.auth = { isAuthenticated: true, user: { email: 'nadia@pellier.example.com', username: 'nadia', signInMethod: 'cognito' } }
    render(<StatusLines messages={[]} />)
    expect(row('Verified identity')).toHaveTextContent('nadia')
    expect(row('Verified identity')).not.toHaveTextContent('Workshop sign-in')
  })
})
