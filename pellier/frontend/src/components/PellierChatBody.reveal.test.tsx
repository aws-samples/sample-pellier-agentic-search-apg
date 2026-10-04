/**
 * A new turn never sits under a half-revealed answer.
 *
 * The hook marks the earlier answer as history (`live: false`) the moment the
 * shopper sends again; this surface then shows that answer in full at once,
 * with no reveal left running above the new turn.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import PellierChatBody from './PellierChatBody'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const ANSWER = 'Start with the Stoneware Mugs, Set of 2 at $38. They are in stock and ready to give.'

function body(messages: AgentChatMessage[]) {
  return (
    <MemoryRouter>
      <PellierChatBody
        messages={messages}
        sendMessage={vi.fn()}
        retryMessage={vi.fn()}
        onEditRequest={vi.fn()}
        onAuthenticate={vi.fn()}
        addToCart={vi.fn()}
        persona={null}
      />
    </MemoryRouter>
  )
}

describe('the handover between turns', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => vi.useRealTimers())

  it('shows the earlier answer in full the moment the next turn opens', () => {
    const asked: AgentChatMessage = { role: 'user', content: 'a housewarming gift', timestamp: new Date(1) }
    const first: AgentChatMessage = {
      role: 'assistant',
      content: ANSWER,
      timestamp: new Date(2),
      agentStatus: 'complete',
      status: { label: 'Writing your answer', state: 'done' },
      live: true,
    }
    const { container, rerender } = render(body([asked, first]))
    act(() => { vi.advanceTimersByTime(24 * 10) })
    const revealed = container.querySelector('.ec-msg-body')?.textContent ?? ''
    expect(revealed.length).toBeGreaterThan(0)
    expect(revealed.length).toBeLessThan(ANSWER.length)

    // The shopper sends again: the hook settles the first answer and opens the next turn.
    const next: AgentChatMessage[] = [
      asked,
      { ...first, live: false },
      { role: 'user', content: 'and for a small kitchen?', timestamp: new Date(3) },
      { role: 'assistant', content: '', timestamp: new Date(4), agentStatus: 'thinking',
        status: { label: 'Sending your request', state: 'working' }, steps: [], live: true },
    ]
    rerender(body(next))
    const bodies = container.querySelectorAll('.ec-msg-body')
    expect(bodies[0].textContent).toBe(ANSWER)
    expect(bodies[0].querySelector('.tn-prose-live')).toBeNull()
  })
})
