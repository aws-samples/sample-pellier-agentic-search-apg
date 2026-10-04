/**
 * The light, dark and system control.
 *
 * The default is the system preference, the choice persists per browser,
 * and a storage that throws (private mode, blocked site data) still leaves
 * the control working and the attribute on <html> set.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ThemeControl from './ThemeControl'
import { THEME_STORAGE_KEY, resetThemeForTests, resolveTheme } from './theme'

function stubMatchMedia(dark: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('dark') ? dark : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

/* The theme-color meta as index.html declares it, with a ground per theme. */
function mountThemeColorMeta(): HTMLMetaElement {
  const meta = document.createElement('meta')
  meta.setAttribute('name', 'theme-color')
  meta.setAttribute('content', 'unset')
  meta.setAttribute('data-light', 'ground-light')
  meta.setAttribute('data-dark', 'ground-dark')
  document.head.appendChild(meta)
  return meta
}

describe('ThemeControl', () => {
  beforeEach(() => {
    resetThemeForTests()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetThemeForTests()
    document.documentElement.removeAttribute('data-theme')
    document.head.querySelector('meta[name="theme-color"]')?.remove()
  })

  it('moves the browser chrome to the chosen ground', () => {
    stubMatchMedia(false)
    const meta = mountThemeColorMeta()
    render(<ThemeControl />)
    expect(meta.getAttribute('content')).toBe('ground-light')

    fireEvent.click(screen.getByRole('button', { name: 'Dark theme' }))
    expect(meta.getAttribute('content')).toBe('ground-dark')

    fireEvent.click(screen.getByRole('button', { name: 'System theme' }))
    expect(meta.getAttribute('content')).toBe('ground-light')
  })

  it('defaults to the system preference and applies it to <html>', () => {
    stubMatchMedia(true)
    render(<ThemeControl />)

    expect(screen.getByRole('button', { name: 'System theme' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(resolveTheme('system')).toBe('dark')
  })

  it('persists the choice per browser and switches the attribute', () => {
    stubMatchMedia(false)
    render(<ThemeControl />)

    fireEvent.click(screen.getByRole('button', { name: 'Dark theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Light theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    // Back to system clears the stored choice so a later preference change wins.
    fireEvent.click(screen.getByRole('button', { name: 'System theme' }))
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('reads a stored choice on mount', () => {
    stubMatchMedia(false)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    render(<ThemeControl />)

    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('survives a storage that throws', () => {
    stubMatchMedia(false)
    const broken = {
      getItem: () => { throw new Error('blocked') },
      setItem: () => { throw new Error('blocked') },
      removeItem: () => { throw new Error('blocked') },
    }
    vi.stubGlobal('localStorage', broken)
    Object.defineProperty(window, 'localStorage', { configurable: true, value: broken })

    render(<ThemeControl />)
    expect(screen.getByRole('button', { name: 'System theme' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Dark theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')
  })
})
