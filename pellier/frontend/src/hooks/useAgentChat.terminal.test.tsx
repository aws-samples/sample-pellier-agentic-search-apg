/**
 * Turns sent from the terminal (`lab_run.py send`) arrive in Ask Pellier through
 * `/api/chat/watch` and render as typed turns do: the same event handling, a
 * "terminal" source, never kept in the browser, and a watch that reconnects.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sendChatMessageStreaming } from '../services/chat'
import {
  applyStreamEvent,
  completeMessage,
  useAgentChat,
  type AgentChatMessage,
  type TurnEvent,
} from './useAgentChat'

type Frame = Record<string, unknown>

const watches: Array<{ onFrame: (frame: Frame) => void; signal: AbortSignal; fail: (e: Error) => void }> = []
let persona: { id: string; customer_id?: string } | null = { id: 'anna', customer_id: 'CUST-ANNA' }

vi.mock('../contexts/PersonaContext', () => ({ usePersona: () => ({ persona }) }))
vi.mock('../services/chat', () => ({
  checkBackendHealth: vi.fn().mockResolvedValue(true),
  normalizeChatError: vi.fn((error: unknown) => error),
  sendChatMessageStreaming: vi.fn(),
  watchTerminalTurns: vi.fn(
    (onFrame: (frame: Frame) => void, signal: AbortSignal) =>
      new Promise<void>((_resolve, reject) => {
        watches.push({ onFrame, signal, fail: reject })
      }),
  ),
}))

const TURN = 'turn-' + 'b'.repeat(32)
const QUESTION = 'A housewarming gift for a friend who loves slow mornings.'

function frames(replay = false): Frame[] {
  return [
    { type: 'relay_turn', turn_id: TURN, session_id: 'persona-anna-1', message: QUESTION,
      source: 'terminal', started_at: '2026-10-14T12:00:00+00:00', ...(replay ? { replay: true } : {}) },
    { type: 'relay_event', turn_id: TURN, event: { type: 'turn_start', turn_id: TURN,
      principal: { authenticated: true, customerId: 'CUST-ANNA', signInMethod: 'workshop' } } },
    { type: 'relay_event', turn_id: TURN, event: { type: 'status', label: 'Understanding your request' } },
    { type: 'relay_event', turn_id: TURN, event: { type: 'step', id: 'route', label: 'Understanding your request',
      status: 'done', finding: 'Sent to the Catalog agent', tags: ['Router'], builder: {} } },
    { type: 'relay_event', turn_id: TURN, event: { type: 'content_delta', delta: 'For a slow ' } },
    { type: 'relay_event', turn_id: TURN, event: { type: 'content_delta', delta: 'morning, the mugs.' } },
    { type: 'relay_event', turn_id: TURN, event: { type: 'complete',
      response: { response: 'For a slow morning, the mugs.', products: [], suggestions: [], turn_id: TURN } } },
    { type: 'relay_end', turn_id: TURN, outcome: 'complete' },
  ]
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <StrictMode>{children}</StrictMode>
}

// StrictMode mounts effects twice, so the first watch is opened and aborted at once.
function live() {
  return watches.filter(watch => !watch.signal.aborted)
}

function deliver(all: Frame[]) {
  const watch = live().at(-1)!
  act(() => {
    for (const frame of all) watch.onFrame(frame)
  })
}

function terminal(messages: AgentChatMessage[]) {
  return messages.filter(message => message.source === 'terminal')
}

describe('turns sent from the terminal', () => {
  beforeEach(() => {
    watches.length = 0
    persona = { id: 'anna', customer_id: 'CUST-ANNA' }
    localStorage.clear()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders a relayed turn with its source, steps, answer and turn events', async () => {
    const reported: TurnEvent[] = []
    const { result } = renderHook(
      () => useAgentChat({ watchTerminal: true, onTurn: event => reported.push(event) }),
      { wrapper },
    )
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames())

    const [question, answer] = terminal(result.current.messages)
    expect(question).toMatchObject({ role: 'user', content: QUESTION, source: 'terminal', turnId: TURN })
    expect(answer).toMatchObject({
      role: 'assistant', source: 'terminal', turnId: TURN, content: 'For a slow morning, the mugs.',
      agentStatus: 'complete',
      principal: { authenticated: true, customerId: 'CUST-ANNA', signInMethod: 'workshop' },
    })
    expect(answer.steps?.map(step => [step.id, step.status, step.finding])).toEqual([
      ['route', 'done', 'Sent to the Catalog agent']])
    expect(reported.map(event => event.type)).toEqual(['start', 'status', 'step', 'end'])
    expect(reported[0]).toEqual({ type: 'start', query: QUESTION })
  })

  it('starts a replayed turn over instead of doubling its answer', async () => {
    const { result } = renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames().slice(0, 5))
    deliver(frames(true))

    const shown = terminal(result.current.messages)
    expect(shown).toHaveLength(2)
    expect(shown[1].content).toBe('For a slow morning, the mugs.')
  })

  it('keeps a typed stream in its own bubble when a relayed turn lands mid-stream', async () => {
    let onUpdate: (data: unknown) => void = () => {}
    let finish: (value: unknown) => void = () => {}
    vi.mocked(sendChatMessageStreaming).mockImplementationOnce(((_q: string, _h: unknown, cb: (d: unknown) => void) => {
      onUpdate = cb
      return new Promise(resolve => { finish = resolve })
    }) as unknown as typeof sendChatMessageStreaming)
    const { result } = renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    act(() => { void result.current.sendMessage('typed question') })
    await waitFor(() => expect(result.current.isLoading).toBe(true))
    deliver(frames().slice(0, 5))
    act(() => { onUpdate({ type: 'content_delta', delta: 'typed answer' }) })

    const relayed = terminal(result.current.messages).at(-1)
    expect(relayed?.content).not.toContain('typed answer')
    const typed = result.current.messages.find(m => m.role === 'assistant' && m.source !== 'terminal')
    expect(typed?.content).toBe('typed answer')
    await act(async () => { finish({ response: 'typed answer', products: [], suggestions: [] }) })
  })

  it('does not report a replayed turn to the results page', async () => {
    const reported: TurnEvent[] = []
    renderHook(
      () => useAgentChat({ watchTerminal: true, onTurn: event => reported.push(event) }),
      { wrapper },
    )
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames(true))
    expect(reported).toEqual([])
  })

  it('keeps relayed turns out of the browser', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { result } = renderHook(
      () => useAgentChat({ watchTerminal: true, persistKey: 'drawer' }),
      { wrapper },
    )
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames())
    expect(terminal(result.current.messages)).toHaveLength(2)
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(localStorage.getItem('drawer') ?? '').not.toContain(QUESTION)
  })

  it('reconnects after the stream drops', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    await waitFor(() => expect(live()).toHaveLength(1))
    const dropped = live()[0]
    const before = watches.length
    await act(async () => {
      dropped.fail(new Error('dropped'))
      await vi.advanceTimersByTimeAsync(1100)
    })
    await waitFor(() => expect(watches.length).toBe(before + 1))
    expect(live().filter(watch => watch !== dropped)).toHaveLength(1)
  })

  it('watches the new shopper when the shopper changes', async () => {
    const { rerender } = renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    await waitFor(() => expect(live()).toHaveLength(1))
    const first = live()[0]
    persona = { id: 'marco', customer_id: 'CUST-MARCO' }
    rerender()
    await waitFor(() => expect(live()).toHaveLength(1))
    expect(first.signal.aborted).toBe(true)
    expect(live()[0]).not.toBe(first)
  })

  it('drops the old shopper turn and lets the new shopper send when the shopper changes', async () => {
    const calls: Array<{ signal?: AbortSignal; onUpdate: (data: unknown) => void }> = []
    vi.mocked(sendChatMessageStreaming).mockImplementation(((
      _q: string, _h: unknown, onUpdate: (d: unknown) => void,
      _m?: unknown, _g?: unknown, _c?: unknown, signal?: AbortSignal,
    ) => {
      calls.push({ signal, onUpdate })
      return new Promise((_resolve, reject) => {
        signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    }) as unknown as typeof sendChatMessageStreaming)
    const { result, rerender } = renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    act(() => { void result.current.sendMessage('first shopper question') })
    await waitFor(() => expect(calls).toHaveLength(1))

    persona = { id: 'marco', customer_id: 'CUST-MARCO' }
    rerender()
    await waitFor(() => expect(calls[0].signal?.aborted).toBe(true))
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    act(() => { void result.current.sendMessage('second shopper question') })
    await waitFor(() => expect(calls).toHaveLength(2))
    vi.mocked(sendChatMessageStreaming).mockReset()
  })

  it('reports the end of a live turn that a reconnect replayed in flight', async () => {
    const reported: TurnEvent[] = []
    renderHook(
      () => useAgentChat({ watchTerminal: true, onTurn: event => reported.push(event) }),
      { wrapper },
    )
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames().slice(0, 5))
    deliver(frames(true).slice(0, 5))
    deliver(frames().slice(5))
    expect(reported.filter(event => event.type === 'start')).toHaveLength(1)
    expect(reported.at(-1)).toEqual({ type: 'end', outcome: 'complete' })
  })

  it('does not report a finished live turn again when a reconnect replays it', async () => {
    const reported: TurnEvent[] = []
    renderHook(
      () => useAgentChat({ watchTerminal: true, onTurn: event => reported.push(event) }),
      { wrapper },
    )
    await waitFor(() => expect(watches.length).toBeGreaterThan(0))
    deliver(frames())
    const before = reported.length
    deliver(frames(true))
    expect(reported).toHaveLength(before)
    expect(reported.filter(event => event.type === 'end')).toHaveLength(1)
  })

  it('stops a guest turn in flight when a shopper arrives, instead of leaving it thinking', async () => {
    persona = null
    vi.mocked(sendChatMessageStreaming).mockImplementationOnce(((
      _q: string, _h: unknown, _cb: unknown, _m?: unknown, _g?: unknown, _c?: unknown, signal?: AbortSignal,
    ) => new Promise((_resolve, reject) => {
      signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })) as unknown as typeof sendChatMessageStreaming)
    const { result, rerender } = renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    act(() => { void result.current.sendMessage('guest question') })
    await waitFor(() => expect(result.current.isLoading).toBe(true))

    persona = { id: 'anna', customer_id: 'CUST-ANNA' }
    rerender()

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const bubble = result.current.messages.at(-1)
    expect(bubble).toMatchObject({ role: 'assistant', agentStatus: 'complete', stopped: true, live: false })
  })

  it('does not watch without a signed-in shopper or when the panel does not ask', async () => {
    persona = null
    renderHook(() => useAgentChat({ watchTerminal: true }), { wrapper })
    persona = { id: 'anna' }
    renderHook(() => useAgentChat({}), { wrapper })
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(watches).toHaveLength(0)
  })
})

describe('applyStreamEvent and completeMessage', () => {
  const base: AgentChatMessage = { role: 'assistant', content: '', timestamp: new Date(0) }

  it('leaves the message untouched and answers null for an event it does not handle', () => {
    expect(applyStreamEvent(base, { type: 'runtime_timing' })).toBeNull()
    expect(applyStreamEvent(base, { type: 'content_delta', delta: '' })).toBeNull()
  })

  it('is pure: the same event on the same message gives equal results and mutates nothing', () => {
    const before = JSON.stringify(base)
    const event = { type: 'content_delta', delta: 'Hi' }
    expect(applyStreamEvent(base, event)).toEqual(applyStreamEvent(base, event))
    expect(JSON.stringify(base)).toBe(before)
  })

  it('completes a message from the complete response', () => {
    const done = completeMessage({ ...base, status: { label: 'Writing your answer', state: 'working' } }, {
      response: 'Done.', products: [], suggestions: ['More?'], turn_id: TURN,
    })
    expect(done).toMatchObject({ content: 'Done.', agentStatus: 'complete', turnId: TURN,
      suggestions: ['More?'], status: { label: 'Writing your answer', state: 'done' } })
  })
})
