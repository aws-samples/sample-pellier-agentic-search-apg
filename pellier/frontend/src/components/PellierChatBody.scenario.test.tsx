/**
 * Scenario language in the storefront chat body.
 *
 * A persona is a workshop scenario, not a Cognito login. The cover banner
 * used to say "Signed in as Marco", which claimed an authentication that
 * never happened; the verified identity lives on its own status line.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import PellierChatBody from './PellierChatBody'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const MARCO: PersonaSnapshot = {
  id: 'marco',
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

const COMPLETE: AgentChatMessage = {
  role: 'assistant',
  content: 'The linen edit is ready.',
  timestamp: new Date('2026-09-04T09:00:00Z'),
  agentStatus: 'complete',
}

describe('storefront chat scenario language', () => {
  it('names the active persona as a scenario, never as a sign-in', () => {
    render(
      <PellierChatBody
        messages={[COMPLETE]}
        sendMessage={vi.fn()}
        retryMessage={vi.fn()}
        onEditRequest={vi.fn()}
        onAuthenticate={vi.fn()}
        addToCart={vi.fn()}
        persona={MARCO}
      />,
    )

    // A label for the scenario already running, not an instruction to pick
    // one: the banner sits over an open conversation.
    expect(screen.getByText('Scenario: Marco Delgado')).toBeInTheDocument()
    expect(screen.queryByText(/signed in as/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^select scenario/i)).not.toBeInTheDocument()
  })
})
