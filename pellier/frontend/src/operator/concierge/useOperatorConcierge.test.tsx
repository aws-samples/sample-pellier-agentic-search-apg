import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  createConciergeSession: vi.fn(),
  fetchCapabilities: vi.fn(),
  fetchConciergeConfig: vi.fn(),
  fetchConciergeSession: vi.fn(),
  fetchLatestConciergeSession: vi.fn(),
  streamConciergeTurn: vi.fn(),
}))

vi.mock('../../services/operator', () => mocks)

import { UNSETTLED_TURN, WORKING_POLL_MS, useOperatorConcierge } from './useOperatorConcierge'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('useOperatorConcierge client isolation', () => {
  it('returns to the selected conversation without loading a newer thread or creating one', async () => {
    mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchLatestConciergeSession.mockResolvedValue('newer-session')
    mocks.fetchConciergeSession.mockResolvedValue({
      sessionId: 'review-session', customerId: 'CUST-JESSICA', messages: [],
    })
    const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA', { initialSessionId: 'review-session' }))
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))
    expect(result.current.sessionId).toBe('review-session')
    expect(mocks.fetchConciergeSession).toHaveBeenCalledWith('CUST-JESSICA', 'review-session')
    expect(mocks.fetchLatestConciergeSession).not.toHaveBeenCalled()
    expect(mocks.createConciergeSession).not.toHaveBeenCalled()
    expect(mocks.streamConciergeTurn).not.toHaveBeenCalled()
  })

  it.each(['another-client', 'another-session'])('does not show %s as the requested conversation', async mismatch => {
    mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchConciergeSession.mockResolvedValue({
      sessionId: mismatch === 'another-session' ? 'different' : 'review-session',
      customerId: mismatch === 'another-client' ? 'CUST-THEO' : 'CUST-JESSICA',
      messages: [{ content: 'Wrong conversation', turnState: 'complete' }],
    })
    const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA', { initialSessionId: 'review-session' }))
    await waitFor(() => expect(result.current.status).toBe('conversation_unavailable'))
    expect(result.current.messages).toEqual([])
    expect(result.current.composerEnabled).toBe(false)
  })

  it('retries the selected conversation after a read failure without silently switching to latest', async () => {
    mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchConciergeSession.mockRejectedValueOnce(new Error('503')).mockResolvedValue({
      sessionId: 'review-session', customerId: 'CUST-JESSICA', messages: [],
    })
    const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA', { initialSessionId: 'review-session' }))
    await waitFor(() => expect(result.current.status).toBe('conversation_unavailable'))
    await act(async () => { await result.current.retryHistory() })
    expect(result.current.sessionId).toBe('review-session')
    expect(result.current.composerEnabled).toBe(true)
    expect(mocks.fetchLatestConciergeSession).not.toHaveBeenCalled()
  })

  it('does not allow submission before the current client load settles', async () => {
    const latest = deferred<string | null>()
    mocks.fetchCapabilities.mockResolvedValue({
      governedActionsAvailable: false,
    })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchLatestConciergeSession.mockReturnValue(latest.promise)

    const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA'))

    await act(async () => {
      await result.current.submit('Investigate this case')
    })

    expect(result.current.composerEnabled).toBe(false)
    expect(mocks.createConciergeSession).not.toHaveBeenCalled()

    await act(async () => {
      latest.resolve(null)
      await latest.promise
    })
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))
  })

  it('ignores an earlier client load that resolves after the client changes', async () => {
    const oldLatest = deferred<string | null>()
    mocks.fetchCapabilities.mockResolvedValue({
      governedActionsAvailable: false,
    })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchLatestConciergeSession.mockImplementation((clientId: string) =>
      clientId === 'CUST-OLD'
        ? oldLatest.promise
        : Promise.resolve('session-new'),
    )
    mocks.fetchConciergeSession.mockImplementation(
      (clientId: string, sessionId: string) =>
        Promise.resolve({
          sessionId,
          customerId: clientId,
          messages: [
            {
              messageId: clientId === 'CUST-OLD' ? 1 : 2,
              role: 'assistant',
              content: clientId === 'CUST-OLD' ? 'Old client' : 'New client',
              turnId: clientId === 'CUST-OLD' ? 'turn-old' : 'turn-new',
              turnState: 'complete',
              actorType: 'assistant',
              artifact: null,
              artifactVersion: 2,
              createdAt: null,
            },
          ],
        }),
    )

    const { result, rerender } = renderHook(
      ({ clientId }) => useOperatorConcierge(clientId),
      { initialProps: { clientId: 'CUST-OLD' } },
    )

    rerender({ clientId: 'CUST-NEW' })

    await waitFor(() => {
      expect(result.current.messages[0]?.content).toBe('New client')
    })

    await act(async () => {
      oldLatest.resolve('session-old')
      await oldLatest.promise
      await Promise.resolve()
    })

    expect(result.current.sessionId).toBe('session-new')
    expect(result.current.messages[0]?.content).toBe('New client')
  })
})


it('requires explicit recovery when latest history is unavailable', async () => {
  mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
  mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
  mocks.fetchLatestConciergeSession.mockRejectedValue(new Error('503'))
  const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA'))
  await waitFor(() => expect(result.current.status).toBe('conversation_unavailable'))
  expect(result.current.composerEnabled).toBe(false)
  expect(mocks.createConciergeSession).not.toHaveBeenCalled()
  mocks.fetchLatestConciergeSession.mockResolvedValue(null)
  await act(async () => { await result.current.retryHistory() })
  expect(result.current.composerEnabled).toBe(true)
  expect(result.current.sessionId).toBeNull()
})

it('keeps a streamed answer if reloading its durable conversation fails', async () => {
  mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
  mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
  mocks.fetchLatestConciergeSession.mockResolvedValue(null)
  mocks.createConciergeSession.mockResolvedValue({ sessionId: 'session-1' })
  mocks.fetchConciergeSession.mockRejectedValue(new Error('503'))
  mocks.streamConciergeTurn.mockImplementation(async (_client, _session, _message, _key, _step, answer) => {
    answer({ summary: 'The records establish ownership.' })
  })
  const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA'))
  await waitFor(() => expect(result.current.composerEnabled).toBe(true))
  await act(async () => { expect(await result.current.submit('Investigate this case')).toBe(false) })
  expect(result.current.liveAnswer).toEqual({ summary: 'The records establish ownership.' })
  expect(result.current.pendingRequest).toBe('Investigate this case')
  expect(result.current.composerEnabled).toBe(false)
})

it.each(['different-client', 'incomplete'])('requires recovery for a %s conversation after a streamed answer', async (condition) => {
  mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
  mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
  mocks.fetchLatestConciergeSession.mockResolvedValue(null)
  mocks.createConciergeSession.mockResolvedValue({ sessionId: 'session-1' })
  mocks.fetchConciergeSession.mockResolvedValue({
    sessionId: 'session-1',
    customerId: condition === 'different-client' ? 'CUST-OTHER' : 'CUST-JESSICA',
    messages: [{ content: 'Unreconciled conversation', turnState: condition === 'incomplete' ? 'incomplete' : 'complete' }],
  })
  mocks.streamConciergeTurn.mockImplementation(async (_client, _session, _message, _key, _step, answer) => {
    answer({ summary: 'The records establish ownership.' })
  })
  const { result } = renderHook(() => useOperatorConcierge('CUST-JESSICA'))
  await waitFor(() => expect(result.current.composerEnabled).toBe(true))
  await act(async () => { expect(await result.current.submit('Investigate this case')).toBe(false) })
  expect(result.current.liveAnswer?.summary).toBe('The records establish ownership.')
  expect(result.current.messages).toEqual([])
  expect(result.current.status).toBe('conversation_unavailable')
  expect(result.current.composerEnabled).toBe(false)
})

describe('a turn that outlives the page reading it', () => {
  const REQUEST = {
    messageId: 1, role: 'user', content: 'Prepare a return for the linen throw',
    turnId: 'turn-1', turnState: 'incomplete', actorType: 'operator',
    artifact: null, artifactVersion: 2, createdAt: null,
  }
  const answer = (turnState: string, content: string) => ({
    messageId: 2, role: 'assistant', content, turnId: 'turn-1', turnState,
    actorType: 'assistant', artifact: { proposedActions: [] }, artifactVersion: 2,
    createdAt: null,
  })
  const session = (messages: unknown[], openTurn: unknown = null) => ({
    sessionId: 'session-1', customerId: 'CUST-JESSICA', messages, openTurn,
  })
  const RUNNING = session([REQUEST], { turnId: 'turn-1', messageId: 1, state: 'running' })

  function resume() {
    mocks.fetchCapabilities.mockResolvedValue({ governedActionsAvailable: false })
    mocks.fetchConciergeConfig.mockResolvedValue({ composerEnabled: true })
    mocks.fetchLatestConciergeSession.mockResolvedValue('session-1')
    return renderHook(() => useOperatorConcierge('CUST-JESSICA'))
  }

  // Reset, not clear: a queued once-value left by one case must not leak into the next.
  beforeEach(() => { Object.values(mocks).forEach((mock) => mock.mockReset()) })
  afterEach(() => { vi.useRealTimers() })

  it('waits for a running turn, then shows its answer in the same conversation', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mocks.fetchConciergeSession
      .mockResolvedValueOnce(RUNNING)
      .mockResolvedValueOnce(RUNNING)
      .mockResolvedValue(session([REQUEST, answer('complete', 'The throw arrived damaged.')]))
    const { result } = resume()

    await waitFor(() => expect(result.current.status).toBe('working'))
    expect(result.current.openTurn?.state).toBe('running')
    expect(result.current.composerEnabled).toBe(false)
    expect(result.current.error).toBeNull()

    await act(async () => { await vi.advanceTimersByTimeAsync(WORKING_POLL_MS) })
    expect(result.current.status).toBe('working')
    await act(async () => { await vi.advanceTimersByTimeAsync(WORKING_POLL_MS) })
    await waitFor(() => expect(result.current.status).toBe('read_only'))
    expect(result.current.composerEnabled).toBe(true)
    expect(result.current.openTurn).toBeNull()
    expect(result.current.sessionId).toBe('session-1')
    expect(result.current.messages.at(-1)?.content).toBe('The throw arrived damaged.')
    expect(mocks.createConciergeSession).not.toHaveBeenCalled()
  })

  it('ends a wait with the interruption the server recorded, and the composer opens', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const settled = 'This request stopped before an answer was saved. It had already prepared review #12, awaiting a decision.'
    mocks.fetchConciergeSession
      .mockResolvedValueOnce(RUNNING)
      .mockResolvedValue(session([REQUEST, answer('interrupted', settled)]))
    const { result } = resume()
    await waitFor(() => expect(result.current.status).toBe('working'))
    await act(async () => { await vi.advanceTimersByTimeAsync(WORKING_POLL_MS) })
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))
    expect(result.current.messages.at(-1)).toMatchObject({ turnState: 'interrupted', content: settled })
    expect(result.current.sessionId).toBe('session-1')
  })

  it('resumes a settled interruption as a usable conversation, not a new one', async () => {
    mocks.fetchConciergeSession.mockResolvedValue(
      session([REQUEST, answer('interrupted', 'This request stopped before an answer was saved.')]),
    )
    const { result } = resume()
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))
    expect(result.current.status).toBe('read_only')
    expect(result.current.sessionId).toBe('session-1')
    expect(result.current.error).toBeNull()
  })

  it('asks for history again when the server could not settle the turn yet', async () => {
    mocks.fetchConciergeSession
      .mockResolvedValueOnce(session([REQUEST], { turnId: 'turn-1', messageId: 1, state: 'abandoned' }))
      .mockResolvedValue(session([REQUEST, answer('interrupted', 'This request stopped before an answer was saved.')]))
    const { result } = resume()
    await waitFor(() => expect(result.current.status).toBe('conversation_unavailable'))
    expect(result.current.error).toBe(UNSETTLED_TURN)
    expect(result.current.composerEnabled).toBe(false)

    await act(async () => { await result.current.retryHistory() })
    expect(result.current.composerEnabled).toBe(true)
    expect(result.current.sessionId).toBe('session-1')
    expect(mocks.createConciergeSession).not.toHaveBeenCalled()
  })

  it('follows the turn after receiving stops, and clears the draft the server holds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mocks.fetchConciergeSession
      .mockResolvedValueOnce(session([]))
      .mockResolvedValueOnce(RUNNING)
      .mockResolvedValue(session([REQUEST, answer('complete', 'The throw arrived damaged.')]))
    mocks.streamConciergeTurn.mockImplementation(async (_c, _s, _m, _k, step) => {
      step({ kind: 'request', label: 'Request saved', source: 'Aurora', status: 'complete' })
      throw new Error('Receiving stopped')
    })
    const { result } = resume()
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))

    let accepted: boolean | undefined
    await act(async () => { accepted = await result.current.submit(REQUEST.content) })
    expect(accepted).toBe(true)
    expect(result.current.status).toBe('working')
    expect(result.current.pendingRequest).toBeNull()
    expect(result.current.error).toBeNull()

    await act(async () => { await vi.advanceTimersByTimeAsync(WORKING_POLL_MS) })
    await waitFor(() => expect(result.current.status).toBe('read_only'))
    expect(result.current.messages.at(-1)?.content).toBe('The throw arrived damaged.')
  })

  it('keeps the draft when the request never reached the server', async () => {
    mocks.fetchConciergeSession
      .mockResolvedValueOnce(session([]))
      .mockResolvedValue(RUNNING)
    mocks.streamConciergeTurn.mockRejectedValue(new Error('turn_in_progress'))
    const { result } = resume()
    await waitFor(() => expect(result.current.composerEnabled).toBe(true))

    let accepted: boolean | undefined
    await act(async () => { accepted = await result.current.submit('A second request') })
    // Another page's turn is running: wait for it, and keep this request unsent.
    expect(accepted).toBe(false)
    expect(result.current.status).toBe('working')
  })
})
