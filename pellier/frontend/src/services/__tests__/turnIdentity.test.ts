/**
 * Turn identity across the wire.
 *
 * A receipt deep link is only useful if it resolves to the same turn after
 * a reload. That requires a server-minted identifier: an id derived from
 * message position silently points at a different turn once anything is
 * reordered, prepended, or filtered, which is worse than having no link.
 *
 * These tests assert the client captures the backend's `turn_id` from the
 * stream and never synthesizes one.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { sendChatMessageStreaming } from '../chat'

/** Build a fake SSE body from a list of event objects. */
function sseStream(events: Record<string, unknown>[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }
      controller.close()
    },
  })
}

function stubFetch(events: Record<string, unknown>[]) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    body: sseStream(events),
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const COMPLETE = {
  type: 'complete',
  response: {
    response: 'Here are three linen pieces.',
    products: [],
    suggestions: [],
  },
}

describe('turn identity', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('captures the server-minted turn id from turn_start', async () => {
    stubFetch([
      { type: 'turn_start', turn_id: 'turn-abc123', session_id: 'sess-1' },
      COMPLETE,
    ])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    expect(result.turn_id).toBe('turn-abc123')
    expect(result.session_id).toBe('sess-1')
  })

  it('prefers the id on the complete envelope when both are present', async () => {
    stubFetch([
      { type: 'turn_start', turn_id: 'turn-early' },
      {
        type: 'complete',
        response: { ...COMPLETE.response, turn_id: 'turn-final' },
      },
    ])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    expect(result.turn_id).toBe('turn-final')
  })

  it('leaves the turn id undefined when the backend emits none', async () => {
    // A turn without an id must degrade to a session-scoped link, not to a
    // fabricated identifier.
    stubFetch([COMPLETE])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    expect(result.turn_id).toBeUndefined()
  })

  it('never derives an id from message position', async () => {
    stubFetch([COMPLETE])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    // No positional fallbacks: not '0', not 'turn-0', not the index.
    expect(result.turn_id).not.toBe('0')
    expect(result.turn_id).not.toBe('turn-0')
  })

  it('carries the rail decision through to the response', async () => {
    stubFetch([
      { type: 'turn_start', turn_id: 'turn-1', session_id: 'sess-1' },
      {
        type: 'complete',
        response: {
          ...COMPLETE.response,
          rail: 'gateway-mcp',
          railDecision: {
            rail: 'gateway-mcp',
            managedRequested: true,
            available: true,
            reason: null,
          },
        },
      },
    ])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    expect(result.rail).toBe('gateway-mcp')
    expect(result.railDecision?.available).toBe(true)
  })

  it('carries a degradation disclosure when the rail was unavailable', async () => {
    stubFetch([
      { type: 'turn_start', turn_id: 'turn-2' },
      {
        type: 'complete',
        response: {
          ...COMPLETE.response,
          rail: 'in-process',
          railDecision: {
            rail: 'in-process',
            managedRequested: true,
            available: false,
            reason: 'authentication_required',
          },
          degradation: {
            degraded: true,
            reason: 'authentication_required',
            rail: 'in-process',
            capabilitiesRemoved: ['give_store_credit'],
            explanation: 'This is not a Cedar DENY.',
          },
        },
      },
    ])

    const result = await sendChatMessageStreaming('linen', [], () => {})

    expect(result.degradation?.degraded).toBe(true)
    expect(result.degradation?.capabilitiesRemoved).toContain('give_store_credit')
    expect(result.railDecision?.available).toBe(false)
  })

  it('passes turn_start through to the onUpdate consumer', async () => {
    // The Pellier needs the id mid-stream to prepare the receipt link.
    stubFetch([{ type: 'turn_start', turn_id: 'turn-3' }, COMPLETE])
    const seen: string[] = []

    await sendChatMessageStreaming('linen', [], (data) => {
      if (typeof data?.type === 'string') seen.push(data.type)
    })

    expect(seen).toContain('turn_start')
  })
})
