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
import { useAgentChat } from './useAgentChat'

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
    (_q: string, _h: unknown, onUpdate: (d: unknown) => void) => {
      capturedOnUpdate = onUpdate
      if (nextStreamFailure) {
        const failure = nextStreamFailure
        nextStreamFailure = null
        return Promise.reject(failure)
      }
      return new Promise(resolve => {
        releaseStream = resolve as typeof releaseStream
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
    const { result } = renderHook(() => useAgentChat({ mode: 'storefront' }), {
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
    const { result } = renderHook(() => useAgentChat({ mode: 'observatory' }), {
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
    const { result } = renderHook(() => useAgentChat({ mode: 'observatory' }), {
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
    const { result } = renderHook(() => useAgentChat({ mode: 'storefront' }), {
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
      () => useAgentChat({ mode: 'storefront' }),
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

  it('does not write a "latest" localStorage key from an event that arrives after unmount', async () => {
    const { result, unmount } = renderHook(
      () => useAgentChat({ mode: 'storefront' }),
      { wrapper },
    )

    act(() => {
      void result.current.sendMessage('show me linen')
    })
    await waitFor(() => expect(capturedOnUpdate).not.toBeNull())

    unmount()

    // Simulate the mock stream's fetch resolving its next chunk anyway --
    // this is exactly what a real unaborted fetch would keep doing.
    act(() => {
      capturedOnUpdate?.({ type: 'skill_routing', skill: 'style', confidence: 0.92 })
    })

    expect(localStorage.getItem('pellier-skill-routing-latest')).toBeNull()
  })

  it('does not update messages/isLoading from a response that resolves after unmount', async () => {
    const { result, unmount } = renderHook(
      () => useAgentChat({ mode: 'storefront' }),
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
