/**
 * When the dock asks the tour for its answer chapter: once the latest answer
 * has settled with its steps, in the Builder view, where the Identity line and
 * the folded steps are on the page to ring.
 */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PellierChatBody from './PellierChatBody'
import { SPOTLIGHT_SEEN_KEY, TOUR_OPEN_DELAY_MS, TOUR_START_EVENT, chapterSeenKey } from './tourChapters'
import type { TurnStep } from './turn/turnTypes'
import type { AgentChatMessage } from '../hooks/useAgentChat'

const ANNA = { authenticated: true, customerId: 'CUST-ANNA', signInMethod: 'workshop' as const }

const ROUTE: TurnStep = {
  id: 'route', label: 'Understanding your request', status: 'done', finding: 'Sent to the Catalog agent', tags: ['Router'],
}

function answer(over: Partial<AgentChatMessage> = {}): AgentChatMessage {
  return {
    role: 'assistant',
    content: 'The linen edit is ready.',
    timestamp: new Date('2026-09-04T09:00:00Z'),
    agentStatus: 'complete',
    steps: [ROUTE],
    principal: ANNA,
    ...over,
  }
}

function renderBody(messages: AgentChatMessage[], builderView = true) {
  return render(
    <PellierChatBody
      messages={messages}
      sendMessage={vi.fn()}
      retryMessage={vi.fn()}
      onEditRequest={vi.fn()}
      onAuthenticate={vi.fn()}
      addToCart={vi.fn()}
      persona={null}
      builderView={builderView}
    />,
  )
}

let asked: string[]
const hear = (event: Event) => { asked.push((event as CustomEvent<string>).detail) }

function waitForLayout() {
  act(() => { vi.advanceTimersByTime(TOUR_OPEN_DELAY_MS) })
}

beforeEach(() => {
  asked = []
  localStorage.removeItem(chapterSeenKey('answer'))
  sessionStorage.removeItem(SPOTLIGHT_SEEN_KEY)
  window.addEventListener(TOUR_START_EVENT, hear)
  vi.useFakeTimers()
})

afterEach(() => {
  window.removeEventListener(TOUR_START_EVENT, hear)
  vi.useRealTimers()
})

describe('the answer chapter of the tour', () => {
  it('is asked for once the latest answer has settled with its steps', () => {
    renderBody([answer()])
    expect(asked).toEqual([])
    waitForLayout()
    expect(asked).toEqual(['answer'])
  })

  it('is asked for once when the dock holds several answers', () => {
    renderBody([answer(), answer(), answer()])
    waitForLayout()
    expect(asked).toEqual(['answer'])
  })

  it('waits for the Builder view, where the evidence shows', () => {
    const view = renderBody([answer()], false)
    waitForLayout()
    expect(asked).toEqual([])

    view.rerender(
      <PellierChatBody
        messages={[answer()]}
        sendMessage={vi.fn()}
        retryMessage={vi.fn()}
        onEditRequest={vi.fn()}
        onAuthenticate={vi.fn()}
        addToCart={vi.fn()}
        persona={null}
        builderView
      />,
    )
    waitForLayout()
    expect(asked).toEqual(['answer'])
  })

  it('is not asked for by an answer restored after a reload, which shows no Identity line', () => {
    renderBody([answer({ principal: undefined })])
    waitForLayout()
    expect(asked).toEqual([])
  })

  it('waits for a complete answer to finish settling in on screen', () => {
    renderBody([answer({ live: true, content: 'A long answer. '.repeat(20) })])
    waitForLayout()
    expect(asked).toEqual([])

    // The reveal paces itself frame by frame, each one drawn before the next is due.
    for (let frame = 0; frame < 2000 && asked.length === 0; frame += 1) {
      act(() => { vi.advanceTimersByTime(250) })
    }
    expect(asked).toEqual(['answer'])
  })

  it('is not asked for while the answer is still streaming', () => {
    renderBody([answer({ live: true, agentStatus: 'streaming' })])
    waitForLayout()
    expect(asked).toEqual([])
  })

  it('is not asked for by an answer that failed or ran no step', () => {
    renderBody([answer({ failure: { code: 'service_unavailable', retryable: true, query: 'linen' } })])
    waitForLayout()
    renderBody([answer({ steps: [] })])
    waitForLayout()
    expect(asked).toEqual([])
  })

  it('is not asked for again in a browser that has seen it', () => {
    localStorage.setItem(chapterSeenKey('answer'), 'true')
    renderBody([answer()])
    waitForLayout()
    expect(asked).toEqual([])
  })
})
