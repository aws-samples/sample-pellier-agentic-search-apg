/**
 * The presence pill must not claim a concierge that is not there.
 *
 * "Concierge online" used to be a hardcoded default: the pill said online
 * with the backend stopped, and the trailing fragment said "14h memory" for
 * Marco from a table of literals that described no session. Both are claims
 * about live systems, so both now come from those systems or are omitted.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '../services/apiBase'
import { HEALTH_FRESH_MS, HEALTH_TIMEOUT_MS, PresencePill } from './PresencePill'

function pill(): HTMLElement {
  return screen.getByTestId('presence-pill-pellier')
}

describe('PresencePill health', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('reads health through the shared API client, not a bare path', async () => {
    // A bare `/api/health` 404s the moment the API is served from another
    // origin, and the pill then reports offline on a healthy system: exactly
    // the inversion it exists to prevent.
    const requested: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        requested.push(String(input))
        return new Response('{}', { status: 200 })
      }),
    )
    render(<PresencePill surface="pellier" />)

    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))
    expect(requested).toContain(`${API_BASE_URL}/api/health`)
  })

  it('goes offline when no check has succeeded for the freshness window', async () => {
    // The first check answers, the rest never settle: a hung health endpoint
    // is what makes a cadence claim into a measurement claim.
    let answered = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        if (answered) return new Promise<Response>(() => {})
        answered = true
        return Promise.resolve(new Response('{}', { status: 200 }))
      }),
    )
    render(<PresencePill surface="pellier" />)
    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))

    await vi.advanceTimersByTimeAsync(HEALTH_FRESH_MS + 1_000)

    expect(pill()).toHaveTextContent('Concierge offline')
  })

  it('abandons a health check that does not answer in time', async () => {
    const signals: AbortSignal[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.signal) signals.push(init.signal)
        // Reject on abort the way fetch does. A mock that ignores the signal
        // hangs forever, so the hook never learns the check failed and the
        // label assertion below can only pass by accident.
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        })
      }),
    )
    render(<PresencePill surface="pellier" />)

    await waitFor(() => expect(signals.length).toBeGreaterThan(0))
    expect(signals[0].aborted).toBe(false)

    await vi.advanceTimersByTimeAsync(HEALTH_TIMEOUT_MS + 100)

    expect(signals[0].aborted).toBe(true)
    // waitFor, not a bare assertion: the abort has to propagate through the
    // fetch rejection and a state update before the label changes. The bare
    // form passed vacuously while "offline" was also the initial state.
    await waitFor(() => expect(pill()).toHaveTextContent('Concierge offline'))
  })

  it('claims neither online nor offline before the first check answers', async () => {
    // An unanswered request is not evidence of an unreachable backend. The pill
    // used to render "offline" for the whole first round trip, which in a
    // workshop room reads as a broken system rather than a pending request.
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    render(<PresencePill surface="pellier" />)

    expect(pill()).toHaveTextContent('Concierge checking')
    expect(pill()).not.toHaveTextContent('Concierge online')
    expect(pill()).not.toHaveTextContent('Concierge offline')
    expect(pill()).toHaveAttribute('data-reachable', 'unknown')
  })

  it('says offline once a check has actually failed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 503 })))
    render(<PresencePill surface="pellier" />)

    await waitFor(() => expect(pill()).toHaveTextContent('Concierge offline'))
    expect(pill()).toHaveAttribute('data-reachable', 'false')
  })

  it('says online after /api/health answers', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    render(<PresencePill surface="pellier" />)

    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/api/health`,
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('updates immediately after the development effect remount', async () => {
    const signals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal) signals.push(init.signal)
      return new Response('{}', { status: 200 })
    }))
    render(<StrictMode><PresencePill surface="pellier" /></StrictMode>)

    // A successful response must update the label before the 15-second poll.
    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))
    expect(signals[0].aborted).toBe(true)
  })

  it('falls back to offline when a later poll fails', async () => {
    let healthy = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: healthy ? 200 : 503 })),
    )
    render(<PresencePill surface="pellier" />)
    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))

    healthy = false
    await vi.advanceTimersByTimeAsync(30_000)

    await waitFor(() => expect(pill()).toHaveTextContent('Concierge offline'))
  })
})

describe('PresencePill API origin', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('prefixes both requests with a configured API origin', async () => {
    vi.stubEnv('VITE_API_URL', 'https://pellier-api.test')
    vi.resetModules()
    const requested: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        requested.push(String(input))
        return new Response('{}', { status: 200 })
      }),
    )

    const { PresencePill: Pill } = await import('./PresencePill')
    render(<Pill surface="pellier" personaId="marco" />)

    await waitFor(() => expect(requested.length).toBeGreaterThanOrEqual(2))
    expect(requested).toContain('https://pellier-api.test/api/health')
    expect(requested).toContain(
      'https://pellier-api.test/api/observatory/memory/marco',
    )
    expect(requested.some((url) => url.startsWith('/api/'))).toBe(false)
  })
})

describe('PresencePill memory age', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('omits the age when the memory endpoint reports no event timestamp', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        expect(url.startsWith(`${API_BASE_URL}/api/`)).toBe(true)
        if (url.includes('/api/observatory/memory/')) {
          return new Response(
            JSON.stringify({ persona: 'marco', working: { items: [] } }),
            { status: 200 },
          )
        }
        return new Response('{}', { status: 200 })
      }),
    )
    render(<PresencePill surface="pellier" personaId="marco" />)

    await waitFor(() => expect(pill()).toHaveTextContent('marco'))
    expect(pill()).not.toHaveTextContent(/memory/)
  })

  it('derives the age from the newest memory event', async () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/observatory/memory/marco')) {
          return new Response(
            JSON.stringify({
              persona: 'marco',
              working: {
                items: [
                  { id: '1', content: 'older', timestamp: '2020-01-01T00:00:00Z' },
                  { id: '2', content: 'newest', timestamp: twoHoursAgo },
                ],
              },
            }),
            { status: 200 },
          )
        }
        return new Response('{}', { status: 200 })
      }),
    )
    render(<PresencePill surface="pellier" personaId="marco" />)

    await waitFor(() => expect(pill()).toHaveTextContent('2h memory'))
  })

  it('never invents an age for an anonymous visitor', async () => {
    const requested: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        requested.push(String(input))
        return new Response('{}', { status: 200 })
      }),
    )
    render(<PresencePill surface="pellier" />)

    await waitFor(() => expect(pill()).toHaveTextContent('Concierge online'))
    expect(pill()).not.toHaveTextContent(/memory/)
    expect(requested.filter((url) => url.includes('/memory/'))).toHaveLength(0)
  })
})
