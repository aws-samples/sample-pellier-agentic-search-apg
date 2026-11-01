/**
 * Session hydration must never overwrite a question typed before the
 * backend's stored turns arrive.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PersonaProvider } from '../contexts/PersonaContext'
import { useAgentChat } from './useAgentChat'

vi.mock('../services/chat', () => ({
  checkBackendHealth: vi.fn().mockResolvedValue(true),
  normalizeChatError: vi.fn((error: unknown) => error),
  sendChatMessageStreaming: vi.fn(() => new Promise(() => undefined)),
}))

let releaseSession: ((turns: unknown[]) => void) | null = null

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).includes('/api/agent/session/')) {
      return new Promise<Response>(resolve => {
        releaseSession = turns => resolve({ ok: true, json: () => Promise.resolve({ turns }) } as Response)
      })
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) } as Response)
  }))
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <PersonaProvider>{children}</PersonaProvider>
}

describe('useAgentChat session hydration', () => {
  beforeEach(() => {
    releaseSession = null
    localStorage.clear()
    stubFetch()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps a question typed before the stored turns arrive', async () => {
    const { result } = renderHook(() => useAgentChat({ sessionId: 's1' }), { wrapper })
    await waitFor(() => expect(releaseSession).not.toBeNull())

    act(() => { void result.current.sendMessage('show me linen') })
    await waitFor(() => expect(result.current.messages.some(m => m.content === 'show me linen')).toBe(true))

    await act(async () => {
      releaseSession!([{ role: 'user', content: 'older question' }, { role: 'assistant', content: 'older answer' }])
    })

    expect(result.current.messages.map(m => m.content)).toContain('show me linen')
    expect(result.current.messages.map(m => m.content)).not.toContain('older question')
  })

  it('hydrates the stored turns when nothing has been typed', async () => {
    const { result } = renderHook(() => useAgentChat({ sessionId: 's1' }), { wrapper })
    await waitFor(() => expect(releaseSession).not.toBeNull())

    await act(async () => {
      releaseSession!([{ role: 'user', content: 'older question' }, { role: 'assistant', content: 'older answer' }])
    })

    expect(result.current.messages.map(m => m.content)).toEqual(
      expect.arrayContaining(['older question', 'older answer']),
    )
  })
})
