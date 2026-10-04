/**
 * The light, dark and system theme choice.
 *
 * The choice persists per browser under `pellier-theme`. The resolved theme
 * is written to `data-theme` on `<html>`, which daylight-tokens.css switches
 * on. The inline script in `index.html` performs the same resolution before
 * first paint so the page never flashes the wrong theme; keep the two in
 * step. Storage can be absent or throw (private mode, blocked site data), so
 * every access is wrapped and the control still works without it.
 */
import { useCallback, useSyncExternalStore } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'pellier-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

const CHOICES: ReadonlyArray<ThemeChoice> = ['light', 'dark', 'system']

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return typeof value === 'string' && (CHOICES as ReadonlyArray<string>).includes(value)
}

export function readStoredChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isThemeChoice(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

function writeStoredChoice(choice: ThemeChoice): void {
  try {
    if (choice === 'system') window.localStorage.removeItem(THEME_STORAGE_KEY)
    else window.localStorage.setItem(THEME_STORAGE_KEY, choice)
  } catch {
    // Storage is optional: the attribute on <html> still carries the theme.
  }
}

export function systemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'light'
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  return choice === 'system' ? systemTheme() : choice
}

export function applyTheme(resolved: ResolvedTheme): void {
  document.documentElement.setAttribute('data-theme', resolved)
}

let currentChoice: ThemeChoice | null = null
const listeners = new Set<() => void>()
let watchingSystem = false

function notify(): void {
  for (const listener of listeners) listener()
}

function watchSystem(): void {
  if (watchingSystem || typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  const media = window.matchMedia(DARK_QUERY)
  if (typeof media.addEventListener !== 'function') return
  watchingSystem = true
  media.addEventListener('change', () => {
    if (getChoice() === 'system') {
      applyTheme(systemTheme())
      notify()
    }
  })
}

export function getChoice(): ThemeChoice {
  if (currentChoice === null) currentChoice = readStoredChoice()
  return currentChoice
}

export function setChoice(choice: ThemeChoice): void {
  currentChoice = choice
  writeStoredChoice(choice)
  applyTheme(resolveTheme(choice))
  notify()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  watchSystem()
  return () => {
    listeners.delete(listener)
  }
}

/** Reset the module between tests. */
export function resetThemeForTests(): void {
  currentChoice = null
  listeners.clear()
}

export function useTheme(): {
  choice: ThemeChoice
  resolved: ResolvedTheme
  setChoice: (choice: ThemeChoice) => void
} {
  const choice = useSyncExternalStore(subscribe, getChoice, () => 'system' as ThemeChoice)
  const set = useCallback((next: ThemeChoice) => setChoice(next), [])
  return { choice, resolved: resolveTheme(choice), setChoice: set }
}
