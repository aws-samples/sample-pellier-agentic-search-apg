/**
 * useObservatoryData — a 404 must not read as "temporarily unavailable".
 *
 * A 404 means this specific record does not exist (a stale link, a typo'd
 * id); a 500/503 means the evidence service is degraded. Telling a
 * participant to "try again" for the first case is dishonest -- retrying
 * the same id never resolves it -- and VOICE.md/PRODUCT.md both require
 * unavailable/not-found to stay distinct failure states. `errorStatus` was
 * already threaded through for a caller to branch on, but the `error`
 * message itself collapsed every non-401/403 status into one string,
 * so a caller reading only `error` could not tell the two apart.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useObservatoryData } from './useObservatoryData'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useObservatoryData — status-specific failure messages', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reports a not-found message and errorStatus 404 on a 404 response', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: 'Session evidence not found.' }, 404),
    )

    const { result } = renderHook(() =>
      useObservatoryData({ key: 'session-does-not-exist' }),
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.errorStatus).toBe(404)
    expect(result.current.error).toBe('This evidence could not be found.')
    expect(result.current.data).toBeNull()
  })

  it('reports the generic unavailable message and errorStatus 503 on a 503 response, distinct from 404', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Aurora unreachable.' }, 503))

    const { result } = renderHook(() => useObservatoryData({ key: 'sessions' }))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.errorStatus).toBe(503)
    expect(result.current.error).toBe(
      'This evidence is temporarily unavailable. Please try again.',
    )
    expect(result.current.error).not.toBe('This evidence could not be found.')
  })
})
