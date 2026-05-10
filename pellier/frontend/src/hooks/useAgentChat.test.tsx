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

vi.mock('../services/chat', () => ({
  checkBackendHealth: vi.fn().mockResolvedValue(true),
  sendChatMessageStreaming: vi.fn(
    (_q: string, _h: unknown, onUpdate: (d: unknown) => void) => {
      capturedOnUpdate = onUpdate
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
    const { result } = renderHook(() => useAgentChat({ mode: 'atelier' }), {
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
    const { result } = renderHook(() => useAgentChat({ mode: 'atelier' }), {
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
})
