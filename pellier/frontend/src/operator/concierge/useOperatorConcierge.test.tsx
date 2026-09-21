import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  createConciergeSession: vi.fn(),
  fetchCapabilities: vi.fn(),
  fetchConciergeConfig: vi.fn(),
  fetchConciergeSession: vi.fn(),
  fetchLatestConciergeSession: vi.fn(),
  streamConciergeTurn: vi.fn(),
}))

vi.mock('../../services/operator', () => mocks)

import { useOperatorConcierge } from './useOperatorConcierge'

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
