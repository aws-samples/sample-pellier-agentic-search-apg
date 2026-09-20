import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_REQUEST_TIMEOUT_MS,
  AuthProvider,
  useAuth,
} from './AuthContext'

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

function clearCookie(name: string) {
  document.cookie = `${name}=; Max-Age=0; path=/`
}

function okJson(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockAuthFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/api/auth/me')) {
      return okJson({
        userId: 'user-1',
        email: 'avery@example.com',
        givenName: 'Avery',
      })
    }
    if (url.includes('/api/user/preferences')) {
      return okJson({ preferences: null })
    }
    return okJson({})
  })
}

const originalLocation = window.location

function installLocation(pathname: string, search = '') {
  const assign = vi.fn()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      ...originalLocation,
      assign,
      pathname,
      search,
    },
  })
  return assign
}

describe('AuthContext hydration', () => {
  beforeEach(() => {
    localStorage.clear()
    clearCookie('just_signed_in')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    localStorage.clear()
    clearCookie('just_signed_in')
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
  })

  it('checks the server cookie even when no readable auth marker exists', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({ detail: 'authentication_required' }),
      {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      },
    ))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.user).toBeNull()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('hydrates the code-flow callback path when just_signed_in is present', async () => {
    const fetchMock = mockAuthFetch()
    vi.stubGlobal('fetch', fetchMock)
    document.cookie = 'just_signed_in=1; path=/'

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.user?.email).toBe('avery@example.com')
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(localStorage.getItem('pellier-auth-session')).toBe('1')
  })

  it('uses the auth-session marker to hydrate later cookie-backed loads', async () => {
    const fetchMock = mockAuthFetch()
    vi.stubGlobal('fetch', fetchMock)
    localStorage.setItem('pellier-auth-session', '1')

    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.user?.email).toBe('avery@example.com')
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('finishes hydration when the auth endpoint does not respond', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('The auth request timed out.', 'AbortError'))
          })
        })
      }),
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTH_REQUEST_TIMEOUT_MS)
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.user).toBeNull()
    expect(result.current.authUnavailable).toBe(true)
  })

  it('preserves the last verified session during an outage and recovers on retry', async () => {
    installLocation('/observatory')
    const fetchMock = mockAuthFetch()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 503 }))
    await act(async () => result.current.refresh())
    expect(result.current.user?.email).toBe('avery@example.com')
    expect(result.current.authUnavailable).toBe(true)
    expect(localStorage.getItem('pellier-auth-session')).toBe('1')
    await act(async () => result.current.refresh())
    expect(result.current.authUnavailable).toBe(false)
    expect(result.current.user?.email).toBe('avery@example.com')
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
    await act(async () => result.current.refresh())
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('pellier-auth-session')).toBeNull()
  })

  it('renews an expired access cookie before clearing a valid session', async () => {
    const fetchMock = mockAuthFetch()
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(okJson({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user?.email).toBe('avery@example.com')
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/auth/me', '/api/auth/refresh', '/api/auth/me', '/api/user/preferences',
    ])
  })

  it('does not sign out or start preferences onboarding when preferences cannot be read', async () => {
    const fetchMock = mockAuthFetch()
    fetchMock.mockImplementation(async input => {
      if (String(input).includes('/preferences')) throw new TypeError('network unavailable')
      return okJson({ userId: 'user-1', email: 'avery@example.com' })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user?.email).toBe('avery@example.com')
    expect(result.current.authUnavailable).toBe(false)
    expect(result.current.preferencesUnavailable).toBe(true)
  })

  it('does not let an older response replace a newer verified identity', async () => {
    const fetchMock = mockAuthFetch()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    let resolveOld!: (value: Response) => void
    fetchMock.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    let older!: Promise<void>
    act(() => { older = result.current.refresh() })
    fetchMock.mockResolvedValueOnce(okJson({ userId: 'user-2', email: 'second@example.com' }))
    await act(async () => result.current.refresh())
    await act(async () => {
      resolveOld(okJson({ userId: 'user-1', email: 'avery@example.com' }))
      await older
    })
    expect(result.current.user?.email).toBe('second@example.com')
  })

  it('retains preferences only for the same verified identity during an outage', async () => {
    const previous = { vibe: [], colors: [], occasions: [], categories: [] }
    const fetchMock = mockAuthFetch()
    fetchMock.mockResolvedValueOnce(okJson({ userId: 'user-1', email: 'avery@example.com' }))
      .mockResolvedValueOnce(okJson({ preferences: previous }))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.preferences).toEqual(previous)
    fetchMock.mockResolvedValueOnce(okJson({ userId: 'user-1', email: 'avery@example.com' }))
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
    await act(async () => result.current.refresh())
    expect(result.current.preferences).toEqual(previous)

    let resolvePreferences!: (response: Response) => void
    fetchMock.mockResolvedValueOnce(okJson({ userId: 'user-2', email: 'second@example.com' }))
      .mockImplementationOnce(() => new Promise(resolve => { resolvePreferences = resolve }))
    let refresh!: Promise<void>
    act(() => { refresh = result.current.refresh() })
    await waitFor(() => expect(result.current.user?.sub).toBe('user-2'))
    expect(result.current.preferences).toBeNull()
    expect(result.current.preferencesUnavailable).toBe(true)
    await act(async () => {
      resolvePreferences(new Response(null, { status: 503 }))
      await refresh
    })
    expect(result.current.preferences).toBeNull()
    expect(result.current.preferencesUnavailable).toBe(true)
  })

  it('does not apply an earlier identity’s saved-preference response to a new session', async () => {
    const previous = { vibe: [], colors: [], occasions: [], categories: [] }
    const fetchMock = mockAuthFetch()
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    let resolveSave!: (response: Response) => void
    fetchMock.mockImplementationOnce(() => new Promise(resolve => { resolveSave = resolve }))
    let save!: Promise<void>
    act(() => { save = result.current.savePreferences(previous) })
    fetchMock.mockResolvedValueOnce(okJson({ userId: 'user-2', email: 'second@example.com' }))
    await act(async () => result.current.refresh())
    await act(async () => {
      resolveSave(okJson({ preferences: previous }))
      await save
    })
    expect(result.current.user?.sub).toBe('user-2')
    expect(result.current.preferences).toBeNull()
    expect(result.current.prefsVersion).toBe(0)
  })

  it('returns browser sign-in to the current SPA route', async () => {
    const assign = installLocation(
      '/operator/clients/CUST-JESSICA',
      '?view=request',
    )
    vi.stubGlobal('fetch', vi.fn())
    const { result } = renderHook(() => useAuth(), { wrapper })

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    act(() => result.current.login())

    expect(assign).toHaveBeenCalledWith(
      `/signin?returnTo=${encodeURIComponent(
        '/operator/clients/CUST-JESSICA?view=request',
      )}`,
    )
  })
})
