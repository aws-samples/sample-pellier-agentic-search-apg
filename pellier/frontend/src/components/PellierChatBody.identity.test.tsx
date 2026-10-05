/**
 * Identity in the storefront chat body.
 *
 * Choosing a shopper signs in with their demo account, so the cover banner
 * names whose edit this is. Who the server verified is a separate fact, from
 * the turn's own `turn_start`: the Builder view shows it on every turn, and
 * it never comes from the shopper on screen.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import PellierChatBody from './PellierChatBody'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const MARCO: PersonaSnapshot = {
  id: 'marco',
  edit: 'marco',
  display_name: 'Marco Delgado',
  role_tag: 'Returning',
  avatar_color: '#5a3528',
  avatar_initial: 'M',
  customer_id: 'CUST-MARCO',
  hero_image: '/assets/personas/marco-720.webp',
  hero_alt: 'Marco',
  hero_subheadline: 'Resort edit',
  stats: { visits: 11, orders: 7, last_seen_days: 21 },
}

function answer(over: Partial<AgentChatMessage> = {}): AgentChatMessage {
  return {
    role: 'assistant',
    content: 'The linen edit is ready.',
    timestamp: new Date('2026-09-04T09:00:00Z'),
    agentStatus: 'complete',
    ...over,
  }
}

function renderBody(messages: AgentChatMessage[], builderView: boolean, persona: PersonaSnapshot | null = MARCO) {
  return render(
    <PellierChatBody
      messages={messages}
      sendMessage={vi.fn()}
      retryMessage={vi.fn()}
      onEditRequest={vi.fn()}
      onAuthenticate={vi.fn()}
      addToCart={vi.fn()}
      persona={persona}
      builderView={builderView}
    />,
  )
}

describe('identity in the storefront chat', () => {
  it("names the shopper's edit on the cover, not a scenario", () => {
    renderBody([answer()], false)
    expect(screen.getByText("Marco Delgado's edit")).toBeInTheDocument()
    expect(screen.queryByText(/scenario/i)).not.toBeInTheDocument()
  })

  it('shows the verified principal on every turn in the Builder view', () => {
    const theo = { authenticated: true, customerId: 'CUST-THEO', signInMethod: 'workshop' as const }
    const anna = { authenticated: true, customerId: 'CUST-ANNA', signInMethod: 'workshop' as const }
    renderBody([answer({ principal: theo }), answer({ principal: anna })], true)
    const lines = screen.getAllByTestId('turn-principal').map(line => line.textContent)
    expect(lines).toEqual(['IdentityWorkshop sign-in, CUST-THEO', 'IdentityWorkshop sign-in, CUST-ANNA'])
  })

  it('says not signed in for a signed-out turn, whatever shopper is on screen', () => {
    const anonymous = { authenticated: false, customerId: null, signInMethod: null }
    renderBody([answer({ principal: anonymous })], true)
    expect(screen.getByTestId('turn-principal')).toHaveTextContent('Not signed in')
    expect(screen.getByTestId('turn-principal')).not.toHaveTextContent('CUST-MARCO')
  })

  it('names a typed sign-in plainly and a staff session as no customer account', () => {
    const nadia = { authenticated: true, customerId: null, signInMethod: 'cognito' as const }
    renderBody([answer({ principal: nadia })], true, null)
    expect(screen.getByTestId('turn-principal')).toHaveTextContent('Signed in, no customer account')
  })

  it('keeps the principal out of the shopper view', () => {
    const theo = { authenticated: true, customerId: 'CUST-THEO', signInMethod: 'workshop' as const }
    renderBody([answer({ principal: theo })], false)
    expect(screen.queryByTestId('turn-principal')).not.toBeInTheDocument()
  })
})
