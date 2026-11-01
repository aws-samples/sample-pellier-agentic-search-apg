/**
 * ?reset=1 clears the stores and reloads; React must not mount in between.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const render = vi.hoisted(() => vi.fn())
vi.mock('react-dom/client', () => ({
  default: { createRoot: vi.fn(() => ({ render })) },
  createRoot: vi.fn(() => ({ render })),
}))
vi.mock('./App.tsx', () => ({ default: () => null }))

const replace = vi.fn()

function visit(search: string) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { pathname: '/', search, replace },
  })
}

describe('main entry', () => {
  const original = window.location

  beforeEach(() => {
    vi.resetModules()
    render.mockClear()
    replace.mockClear()
    document.body.innerHTML = '<div id="root"></div>'
    localStorage.setItem('pellier-session-id', 'persona-anna-1')
  })
  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: original })
  })

  it('mounts the app on an ordinary visit', async () => {
    visit('')
    await import('./main.tsx')
    expect(render).toHaveBeenCalledTimes(1)
    expect(replace).not.toHaveBeenCalled()
    expect(localStorage.getItem('pellier-session-id')).toBe('persona-anna-1')
  })

  it('clears the stores and reloads without mounting React on ?reset=1', async () => {
    visit('?reset=1')
    await import('./main.tsx')
    expect(localStorage.getItem('pellier-session-id')).toBeNull()
    expect(replace).toHaveBeenCalledWith('/')
    expect(render).not.toHaveBeenCalled()
  })
})
