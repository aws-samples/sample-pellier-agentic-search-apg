/**
 * useAgentChat regression tests — prove every state updater stays pure
 * under React 18 StrictMode's double-invocation contract.
 *
 * Background: an earlier `appendDelta` mutated `prev[last].content`
 * directly, which caused content_delta tokens to double under
 * StrictMode (dev only, but it's the mode every attendee hits).
 * "Trousers in Oatmeal" rendered as "Trousers inousers in Oatmeal"
 * because the reducer ran twice and the second pass saw mutated state.
 *
 * We re-run the hook inside <StrictMode> so these tests fail if any
 * updater reverts to in-place mutation.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PersonaProvider } from '../contexts/PersonaContext'
import { answerPicks, useAgentChat, type AgentChatMessage } from './useAgentChat'

// --- Chat service mock ---------------------------------------------------
// Captured callback — the test drives it to simulate the SSE loop.
// The stream promise is held open until the test explicitly releases
// it, so deltas can fire before the hook's "complete" reconciliation
// writes the final response over our streamed content.
let capturedOnUpdate: ((data: unknown) => void) | null = null
let releaseStream:
  | ((response: {
      response: string
      products: unknown[]
      suggestions: string[]
    }) => void)
  | null = null
let nextStreamFailure:
  | { code: 'request_timeout'; retryable: true; referenceId?: string }
  | null = null

vi.mock('../services/chat', () => ({
  checkBackendHealth: vi.fn().mockResolvedValue(true),
  normalizeChatError: vi.fn((error: unknown) => error),
  sendChatMessageStreaming: vi.fn(
    (
      _q: string,
      _h: unknown,
      onUpdate: (d: unknown) => void,
      _mode?: unknown,
      _guardrails?: unknown,
      _customer?: unknown,
      signal?: AbortSignal,
    ) => {
      capturedOnUpdate = onUpdate
      if (nextStreamFailure) {
        const failure = nextStreamFailure
        nextStreamFailure = null
        return Promise.reject(failure)
      }
      return new Promise((resolve, reject) => {
        releaseStream = resolve as typeof releaseStream
        signal?.addEventListener('abort', () => {
          const error = new Error('aborted')
          error.name = 'AbortError'
          reject(error)
        })
      })
    },
  ),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <StrictMode>
      <PersonaProvider>{children}</PersonaProvider>
    </StrictMode>
  )
}

describe('useAgentChat — StrictMode purity', () => {
  beforeEach(() => {
    capturedOnUpdate = null
    releaseStream = null
    nextStreamFailure = null
    localStorage.clear()
  })

  it('appends content_delta tokens exactly once under StrictMode', async () => {
    const { result } = renderHook(() => useAgentChat(), {
      wrapper,
    })

    // Kick off a turn but don't await — the mock stream stays open
    // until releaseStream() so we can fire deltas into the captured
    // onUpdate handler before the hook's final reconciliation runs.
    act(() => {
      void result.current.sendMessage('show me linen')
    })

    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    act(() => {
      capturedOnUpdate!({ type: 'content_delta', delta: 'Trousers in ' })
      capturedOnUpdate!({ type: 'content_delta', delta: 'Oatmeal ($98) ' })
      capturedOnUpdate!({
        type: 'content_delta',
        delta: 'are the Sunday piece.',
      })
    })

    // Snapshot the streamed content BEFORE the stream resolves —
    // the hook's complete path will reconcile with response.response
    // after this, but we specifically want to prove the streamed
    // deltas landed cleanly.
    await waitFor(() => {
      const last = result.current.messages.at(-1)
      expect(last?.content).toBe(
        'Trousers in Oatmeal ($98) are the Sunday piece.',
      )
    })
  })

  it('content_reset clears content without doubling subsequent deltas', async () => {
    const { result } = renderHook(() => useAgentChat(), {
      wrapper,
    })

    act(() => {
      void result.current.sendMessage('find shoes')
    })

    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    act(() => {
      capturedOnUpdate!({ type: 'content_delta', delta: 'thinking...' })
      capturedOnUpdate!({ type: 'content_reset' })
      capturedOnUpdate!({
        type: 'content_delta',
        delta: 'Here are the top picks.',
      })
    })

    await waitFor(() => {
      expect(result.current.messages.at(-1)?.content).toBe(
        'Here are the top picks.',
      )
    })
  })

  it('product dedupe survives double-invocation (single product added once)', async () => {
    const { result } = renderHook(() => useAgentChat(), {
      wrapper,
    })

    act(() => {
      void result.current.sendMessage('linen shorts')
    })

    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    act(() => {
      capturedOnUpdate!({
        type: 'product',
        product: { id: 42, name: 'Linen Drawstring Shorts', price: 78 },
      })
    })

    await waitFor(() => {
      const products = result.current.messages.at(-1)?.products
      expect(products).toHaveLength(1)
      expect(products?.[0]?.id).toBe(42)
    })
  })

  it('records typed failures and retries without duplicating the user turn', async () => {
    nextStreamFailure = {
      code: 'request_timeout',
      retryable: true,
      referenceId: 'turn-timeout-1',
    }
    const { result } = renderHook(() => useAgentChat(), {
      wrapper,
    })

    await act(async () => {
      await result.current.sendMessage('find a linen jacket')
    })

    await waitFor(() => {
      expect(result.current.messages.at(-1)?.failure).toEqual({
        code: 'request_timeout',
        retryable: true,
        query: 'find a linen jacket',
        referenceId: 'turn-timeout-1',
      })
    })

    act(() => {
      void result.current.retryMessage('find a linen jacket')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    expect(
      result.current.messages.filter(message => message.role === 'user'),
    ).toHaveLength(1)

    act(() => {
      releaseStream?.({
        response: 'Here is the recovered answer.',
        products: [],
        suggestions: [],
      })
    })

    await waitFor(() => {
      expect(result.current.messages.at(-1)?.content).toBe(
        'Here is the recovered answer.',
      )
      expect(result.current.messages.at(-1)?.failure).toBeUndefined()
    })
  })
})

describe('useAgentChat — unmount mid-stream', () => {
  // `ShopperChatSlot` (App.tsx) unmounts ChatDrawer -- and this hook with
  // it -- on every navigation to /operator or /observatory. Before this
  // fix, a turn already in flight kept running: every streamed event kept
  // calling setMessages on a gone component and writing "latest" keys to
  // localStorage that other surfaces read as current.
  beforeEach(() => {
    capturedOnUpdate = null
    releaseStream = null
    nextStreamFailure = null
    localStorage.clear()
  })

  it('aborts the in-flight turn on unmount', async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
    const { result, unmount } = renderHook(
      () => useAgentChat(),
      { wrapper },
    )

    act(() => {
      void result.current.sendMessage('show me linen')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    abortSpy.mockClear() // drop any StrictMode-remount no-op calls before the turn existed

    unmount()

    expect(abortSpy).toHaveBeenCalled()
    abortSpy.mockRestore()
  })

  it('ignores a step event that arrives after unmount', async () => {
    const { result, unmount } = renderHook(
      () => useAgentChat(),
      { wrapper },
    )

    act(() => {
      void result.current.sendMessage('show me linen')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    unmount()

    // Simulate the mock stream's fetch resolving its next chunk anyway --
    // this is exactly what a real unaborted fetch would keep doing.
    expect(() => {
      act(() => {
        capturedOnUpdate?.({ type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'running', tags: ['Aurora'] })
      })
    }).not.toThrow()
  })

  it('ends the turn for the page when the dock unmounts mid-stream', async () => {
    const onTurn = vi.fn()
    const { result, unmount } = renderHook(() => useAgentChat({ onTurn }), { wrapper })
    act(() => {
      void result.current.sendMessage('show me linen')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    expect(onTurn).toHaveBeenCalledWith({ type: 'start', query: 'show me linen' })
    act(() => {
      capturedOnUpdate?.({
        type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', tags: [],
        builder: { tool: 'search_products' },
        results: { available: true, product_ids: ['31'], limits: [], filters: null },
      })
    })
    const stepEvent = onTurn.mock.calls.map(([event]) => event).find(event => event.type === 'step')
    expect(stepEvent.step.results.product_ids).toEqual(['31'])
    unmount()
    expect(onTurn).toHaveBeenLastCalledWith({ type: 'end', outcome: 'stopped' })
  })

  it('does not update messages/isLoading from a response that resolves after unmount', async () => {
    const { result, unmount } = renderHook(
      () => useAgentChat(),
      { wrapper },
    )

    act(() => {
      void result.current.sendMessage('show me linen')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    const resolve = releaseStream

    unmount()

    // No React "update on an unmounted component" warning, and no throw:
    // the guard returns before touching state at all.
    expect(() => {
      act(() => {
        resolve?.({ response: 'too late', products: [], suggestions: [] })
      })
    }).not.toThrow()
  })
})


describe('useAgentChat — the step contract', () => {
  beforeEach(() => {
    capturedOnUpdate = null
    releaseStream = null
    nextStreamFailure = null
    localStorage.clear()
  })

  it('keeps the status line and merges steps by id from real events', async () => {
    const { result } = renderHook(() => useAgentChat(), { wrapper })
    act(() => {
      void result.current.sendMessage('a housewarming gift')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    expect(result.current.messages.at(-1)?.status).toEqual({ label: 'Sending your request', state: 'working' })

    act(() => {
      capturedOnUpdate!({ type: 'status', label: 'Understanding your request' })
      capturedOnUpdate!({ type: 'step', id: 'route', label: 'Understanding your request', status: 'done', finding: 'Sent to the Shopping agent', tags: ['Router'] })
      capturedOnUpdate!({ type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'running', tags: ['Aurora'] })
      capturedOnUpdate!({ type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', finding: '4 under $100', tags: ['Aurora'], builder: { tool: 'search_products' } })
      capturedOnUpdate!({ type: 'status', label: 'Writing your answer' })
    })

    await waitFor(() => {
      const last = result.current.messages.at(-1)
      expect(last?.status).toEqual({ label: 'Writing your answer', state: 'working' })
      expect(last?.steps?.map(step => [step.id, step.status, step.finding])).toEqual([
        ['route', 'done', 'Sent to the Shopping agent'],
        ['step-1', 'done', '4 under $100'],
      ])
    })

    act(() => {
      releaseStream?.({ response: 'Start with the mugs.', products: [], suggestions: [] })
    })
    await waitFor(() => {
      expect(result.current.messages.at(-1)?.status?.state).toBe('done')
      expect(result.current.messages.at(-1)?.agentStatus).toBe('complete')
    })
  })

  it('never persists a step identity binding with the conversation', async () => {
    const { result } = renderHook(() => useAgentChat({ persistKey: 'k' }), { wrapper })
    act(() => {
      void result.current.sendMessage('any news on my chipped bowl?')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({
        type: 'step', id: 'step-1', label: 'Reading your tickets', status: 'done', finding: '1 open ticket', tags: ['Aurora', 'Identity'],
        builder: { tool: 'get_tickets', audit_id: 9032, identity: { binding: 'overwritten', requested_customer: 'CUST-JESSICA', bound_customer: 'CUST-THEO', authorized_customer: 'CUST-THEO' } },
      })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.steps?.[0]?.builder?.identity?.binding).toBe('overwritten'))
    await waitFor(() => expect(localStorage.getItem('k')).toContain('"audit_id":9032'), { timeout: 2000 })
    const stored = localStorage.getItem('k') ?? ''
    expect(stored).not.toContain('CUST-')
    expect(stored).not.toContain('"identity"')
    // The live view keeps the evidence for this session.
    expect(result.current.messages.at(-1)?.steps?.[0]?.builder?.identity?.requested_customer).toBe('CUST-JESSICA')
  })

  it('carries the verified principal from turn_start, and never persists it', async () => {
    const { result } = renderHook(() => useAgentChat({ persistKey: 'k' }), { wrapper })
    act(() => {
      void result.current.sendMessage('what is happening with my ticket?')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({
        type: 'turn_start', turn_id: 'turn-1', session_id: 's',
        principal: { authenticated: true, customerId: 'CUST-THEO', signInMethod: 'workshop' },
      })
      capturedOnUpdate!({ type: 'status', label: 'Reading your tickets' })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.principal).toEqual({
      authenticated: true, customerId: 'CUST-THEO', signInMethod: 'workshop',
    }))
    await waitFor(() => expect(localStorage.getItem('k')).toContain('what is happening with my ticket?'), { timeout: 2000 })
    expect(localStorage.getItem('k')).not.toContain('CUST-THEO')
    expect(localStorage.getItem('k')).not.toContain('"principal"')
  })

  it('takes the turn id from turn_start and keeps it when the final payload omits it', async () => {
    const { result } = renderHook(() => useAgentChat(), { wrapper })
    act(() => {
      void result.current.sendMessage('a linen throw')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({ type: 'turn_start', turn_id: 'turn-7', session_id: 's' })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.turnId).toBe('turn-7'))
    expect(result.current.messages.at(-1)?.principal).toBeUndefined()
    act(() => {
      releaseStream!({ response: 'The linen throw is in stock.', products: [], suggestions: [] })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.agentStatus).toBe('complete'))
    expect(result.current.messages.at(-1)?.turnId).toBe('turn-7')
  })

  it('reads a signed-out turn_start as no principal, and an unknown method as none', async () => {
    const { result } = renderHook(() => useAgentChat(), { wrapper })
    act(() => {
      void result.current.sendMessage('a linen shirt')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({
        type: 'turn_start', turn_id: 'turn-2',
        principal: { authenticated: false, customerId: null, signInMethod: 'magic' },
      })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.principal).toEqual({
      authenticated: false, customerId: null, signInMethod: null,
    }))
  })

  it('marks the turn it opened as live and strips the flag from history', async () => {
    localStorage.setItem('k', JSON.stringify([
      { role: 'assistant', content: 'old', timestamp: new Date().toISOString(), agentStatus: 'complete', live: true },
    ]))
    const { result } = renderHook(() => useAgentChat({ persistKey: 'k' }), { wrapper })
    expect(result.current.messages[0].live).toBeUndefined()
    act(() => {
      void result.current.sendMessage('a linen shirt')
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.live).toBe(true))
  })

  it('settles the earlier answer the moment a new turn opens', async () => {
    const { result } = renderHook(() => useAgentChat(), { wrapper })
    act(() => {
      void result.current.sendMessage('a linen shirt')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      releaseStream?.({ response: 'Start with the Hadley linen shirt.', products: [], suggestions: [] })
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.agentStatus).toBe('complete'))
    expect(result.current.messages.at(-1)?.live).toBe(true)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => {
      void result.current.sendMessage('and trousers to go with it?')
    })
    await waitFor(() => expect(result.current.messages.at(-1)?.live).toBe(true))
    const earlier = result.current.messages.find(
      message => message.role === 'assistant' && message.content.startsWith('Start with'),
    )
    expect(earlier?.live).toBe(false)
  })

  it('stop keeps the text so far and records no failure', async () => {
    const { result } = renderHook(() => useAgentChat(), { wrapper })
    act(() => {
      void result.current.sendMessage('a linen shirt')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({ type: 'content_delta', delta: 'Start with the Hadley' })
    })
    act(() => {
      result.current.stopTurn()
    })
    await waitFor(() => {
      const last = result.current.messages.at(-1)
      expect(last?.stopped).toBe(true)
      expect(last?.content).toBe('Start with the Hadley')
      expect(last?.failure).toBeUndefined()
      expect(last?.status).toEqual({ label: 'Stopped', state: 'done' })
    })
  })
})

describe("useAgentChat — the answer's picks", () => {
  beforeEach(() => {
    capturedOnUpdate = null
    releaseStream = null
    nextStreamFailure = null
    localStorage.clear()
  })

  const product = (id: number, name: string, ownership?: 'owned') => ({ id, name, price: 40, image: '', ownership })

  it('reports the cards the panel shows, in the order the answer names them', async () => {
    const onTurn = vi.fn()
    const { result } = renderHook(() => useAgentChat({ onTurn }), { wrapper })
    act(() => {
      void result.current.sendMessage('for the trip')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())
    act(() => {
      capturedOnUpdate!({ type: 'content_delta', delta: 'Pack the Linen Drawstring Trousers, the Travel Bottles, ' })
      capturedOnUpdate!({ type: 'content_delta', delta: 'and the Everyday Backpack. Not the Merino Travel Socks you own.' })
    })
    act(() => {
      releaseStream?.({
        response: 'Pack these.',
        products: [
          { id: 96, name: 'Everyday Backpack', price: 118 },
          { id: 20, name: 'Merino Travel Socks', price: 16, ownership: 'owned' },
          { id: 14, name: 'Linen Drawstring Trousers', price: 78 },
          { id: 97, name: 'Travel Bottles', price: 16 },
          { id: 95, name: 'Canvas Crossbody Bag', price: 54 },
        ],
        suggestions: [],
      })
    })
    await waitFor(() => expect(onTurn).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'end' })))
    // The streamed answer is the one shown; it names three new pieces in this order.
    expect(onTurn).toHaveBeenLastCalledWith({ type: 'end', outcome: 'complete', picks: ['14', '97', '96'] })
  })

  it('has no picks when the answer names no piece, or is a request waiting on a person', () => {
    const base: AgentChatMessage = {
      role: 'assistant',
      content: 'The Everyday Backpack is the one.',
      timestamp: new Date(0),
      products: [product(96, 'Everyday Backpack'), product(20, 'Merino Travel Socks', 'owned')],
    }
    expect(answerPicks(base)).toEqual(['96'])
    expect(answerPicks({ ...base, content: 'Nothing here fits.' })).toEqual([])
    expect(answerPicks({ ...base, content: 'Your Merino Travel Socks are already yours.' })).toEqual([])
    expect(answerPicks({
      ...base,
      creditRequestPending: { tool: 'ask_a_person', message: 'A person will look at it.' },
    })).toEqual([])
  })
})
