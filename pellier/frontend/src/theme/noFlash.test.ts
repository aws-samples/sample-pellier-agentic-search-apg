/**
 * The inline script in index.html sets `data-theme` before React mounts, so
 * the page never paints the wrong theme. It must sit before the module
 * script and resolve exactly as src/theme/theme.ts does.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const html = readFileSync(resolve(here, '../../index.html'), 'utf8')

function inlineScript(): string {
  const match = html.match(/<script id="pellier-theme-script">([\s\S]*?)<\/script>/)
  if (!match) throw new Error('index.html has no #pellier-theme-script')
  return match[1]
}

interface FakeWindow {
  localStorage?: { getItem: (key: string) => string | null }
  matchMedia?: (query: string) => { matches: boolean }
}

function run(win: FakeWindow): string | null {
  const root = { attribute: null as string | null }
  const doc = {
    documentElement: {
      setAttribute: (name: string, value: string) => {
        if (name === 'data-theme') root.attribute = value
      },
    },
  }
  new Function('window', 'document', inlineScript())(win, doc)
  return root.attribute
}

describe('no-flash theme script', () => {
  it('runs before the module script that mounts React', () => {
    const script = html.indexOf('id="pellier-theme-script"')
    const module = html.indexOf('<script type="module" src="/src/main.tsx">')
    expect(script).toBeGreaterThan(-1)
    expect(module).toBeGreaterThan(script)
  })

  it('applies a stored choice', () => {
    expect(run({ localStorage: { getItem: () => 'dark' }, matchMedia: () => ({ matches: false }) })).toBe('dark')
    expect(run({ localStorage: { getItem: () => 'light' }, matchMedia: () => ({ matches: true }) })).toBe('light')
  })

  it('falls back to the system preference without a stored choice', () => {
    expect(run({ localStorage: { getItem: () => null }, matchMedia: () => ({ matches: true }) })).toBe('dark')
    expect(run({ localStorage: { getItem: () => 'purple' }, matchMedia: () => ({ matches: false }) })).toBe('light')
  })

  it('survives a storage or media query that throws', () => {
    const throwing = { getItem: () => { throw new Error('blocked') } }
    expect(run({ localStorage: throwing, matchMedia: () => ({ matches: true }) })).toBe('dark')
    expect(run({ localStorage: throwing, matchMedia: () => { throw new Error('no media') } })).toBe('light')
  })
})
