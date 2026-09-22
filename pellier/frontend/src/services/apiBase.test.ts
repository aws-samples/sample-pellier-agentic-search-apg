import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.resetModules()
})

async function deployedApi(base = '/ports/8000/') {
  vi.resetModules()
  vi.stubEnv('BASE_URL', base)
  vi.stubEnv('VITE_API_URL', '')
  vi.stubEnv('VITE_API_BASE_URL', '')
  return import('./apiBase')
}

describe('application API routing', () => {
  it('keeps all three surfaces and sign-in beneath the workspace app prefix', async () => {
    const { apiUrl } = await deployedApi()
    for (const path of ['/api/products', '/api/persona/switch', '/api/auth/signin?provider=email',
      '/api/operator/clients', '/api/observatory/proof-board', '/api/chat/stream']) {
      expect(apiUrl(path)).toBe(`/ports/8000${path}`)
    }
    expect(apiUrl('/ports/8000/api/health')).toBe('/ports/8000/api/health')
    expect(apiUrl('https://example.com/api/health')).toBe('https://example.com/api/health')
  })

  it('retains local development and explicit API origins', async () => {
    expect((await deployedApi('/')).apiUrl('/api/health')).toBe('/api/health')
    vi.resetModules()
    vi.stubEnv('VITE_API_URL', 'https://api.example.com/')
    expect((await import('./apiBase')).apiUrl('/api/health')).toBe('https://api.example.com/api/health')
  })

  it('passes through cookies, cancellation and the streaming response without buffering', async () => {
    const response = new Response(new ReadableStream())
    const fetch = vi.fn().mockResolvedValue(response)
    vi.stubGlobal('fetch', fetch)
    const { apiFetch } = await deployedApi()
    const options: RequestInit = { method: 'POST', credentials: 'include',
      body: '{"message":"Help Jessica"}', signal: new AbortController().signal }
    expect(await apiFetch('/api/chat/stream', options)).toBe(response)
    expect(fetch).toHaveBeenCalledWith('/ports/8000/api/chat/stream', options)
  })
})
