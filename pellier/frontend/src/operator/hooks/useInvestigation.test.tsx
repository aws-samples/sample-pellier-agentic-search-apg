import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { InvestigationAnswer } from '../../services/operator'
import { ANSWER } from '../fixtures'

const api = vi.hoisted(() => ({ streamInvestigation: vi.fn() }))

vi.mock('../../services/operator', async () => {
  const actual = await vi.importActual<typeof import('../../services/operator')>('../../services/operator')
  return { ...actual, ...api }
})

import { OperatorApiError } from '../../services/operator'
import { useInvestigation } from './useInvestigation'

/** A stream that stays open until its signal aborts, then rejects as the service does. */
function openStream(code = 'investigation_stopped') {
  return (_id: string, _step: unknown, _answer: unknown, signal: AbortSignal) =>
    new Promise<InvestigationAnswer>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new OperatorApiError(code, 503)))
    })
}

describe('useInvestigation', () => {
  it('stays idle for client B when client A is abandoned mid-stream', async () => {
    api.streamInvestigation.mockImplementation(openStream())
    const { result, rerender } = renderHook(({ id }) => useInvestigation(id), { initialProps: { id: 'A' } })
    act(() => { void result.current.start() })
    await waitFor(() => expect(result.current.phase).toBe('running'))

    rerender({ id: 'B' })
    await act(async () => { await Promise.resolve() })

    expect(result.current.phase).toBe('idle')
    expect(result.current.error).toBeNull()
  })

  it('lands in a stopped state, not failed, when the reader presses Stop', async () => {
    api.streamInvestigation.mockImplementation(openStream())
    const { result } = renderHook(() => useInvestigation('A'))
    act(() => { void result.current.start() })
    await waitFor(() => expect(result.current.phase).toBe('running'))

    await act(async () => { result.current.stop() })

    expect(result.current.phase).toBe('stopped')
    expect(result.current.status?.label).toBe('Investigation stopped')
  })

  it('reports a deadline as its own failure code', async () => {
    api.streamInvestigation.mockRejectedValue(new OperatorApiError('investigation_timeout', 504))
    const { result } = renderHook(() => useInvestigation('A'))
    await act(async () => { await result.current.start() })

    expect(result.current.phase).toBe('failed')
    expect(result.current.error).toBe('investigation_timeout')
  })

  it('still completes a normal run', async () => {
    api.streamInvestigation.mockResolvedValue(ANSWER)
    const { result } = renderHook(() => useInvestigation('A'))
    await act(async () => { await result.current.start() })
    expect(result.current.phase).toBe('done')
  })
})
