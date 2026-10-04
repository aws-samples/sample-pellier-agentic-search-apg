/**
 * The inline script in index.html sets `data-theme` before React mounts, so
 * the page never paints the wrong theme, and points the `theme-color` meta
 * at the matching page ground. It must sit before the module script and
 * resolve exactly as src/theme/theme.ts does.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const html = readFileSync(resolve(here, '../../index.html'), 'utf8')
const tokens = readFileSync(resolve(here, '../styles/daylight-tokens.css'), 'utf8')

function inlineScript(): string {
  const match = html.match(/<script id="pellier-theme-script">([\s\S]*?)<\/script>/)
  if (!match) throw new Error('index.html has no #pellier-theme-script')
  return match[1]
}

interface FakeWindow {
  localStorage?: { getItem: (key: string) => string | null }
  matchMedia?: (query: string) => { matches: boolean }
}

/* The meta as index.html declares it: a ground per theme in data attributes. */
function fakeMeta() {
  const attributes: Record<string, string> = { 'data-light': 'ground-light', 'data-dark': 'ground-dark', content: 'unset' }
  return {
    attributes,
    getAttribute: (name: string) => attributes[name] ?? null,
    setAttribute: (name: string, value: string) => { attributes[name] = value },
  }
}

function run(win: FakeWindow): { theme: string | null; chrome: string } {
  const root = { attribute: null as string | null }
  const meta = fakeMeta()
  const doc = {
    documentElement: {
      setAttribute: (name: string, value: string) => {
        if (name === 'data-theme') root.attribute = value
      },
    },
    querySelector: (selector: string) => (selector === 'meta[name="theme-color"]' ? meta : null),
  }
  new Function('window', 'document', inlineScript())(win, doc)
  return { theme: root.attribute, chrome: meta.attributes.content }
}

describe('no-flash theme script', () => {
  it('runs before the module script that mounts React', () => {
    const script = html.indexOf('id="pellier-theme-script"')
    const module = html.indexOf('<script type="module" src="/src/main.tsx">')
    expect(script).toBeGreaterThan(-1)
    expect(module).toBeGreaterThan(script)
  })

  it('applies a stored choice', () => {
    expect(run({ localStorage: { getItem: () => 'dark' }, matchMedia: () => ({ matches: false }) }).theme).toBe('dark')
    expect(run({ localStorage: { getItem: () => 'light' }, matchMedia: () => ({ matches: true }) }).theme).toBe('light')
  })

  it('falls back to the system preference without a stored choice', () => {
    expect(run({ localStorage: { getItem: () => null }, matchMedia: () => ({ matches: true }) }).theme).toBe('dark')
    expect(run({ localStorage: { getItem: () => 'purple' }, matchMedia: () => ({ matches: false }) }).theme).toBe('light')
  })

  it('survives a storage or media query that throws', () => {
    const throwing = { getItem: () => { throw new Error('blocked') } }
    expect(run({ localStorage: throwing, matchMedia: () => ({ matches: true }) }).theme).toBe('dark')
    expect(run({ localStorage: throwing, matchMedia: () => { throw new Error('no media') } }).theme).toBe('light')
  })

  it('points the browser chrome at the chosen ground, not the system scheme', () => {
    // A dark choice on a light system gets the dark ground.
    expect(run({ localStorage: { getItem: () => 'dark' }, matchMedia: () => ({ matches: false }) }).chrome).toBe('ground-dark')
    expect(run({ localStorage: { getItem: () => null }, matchMedia: () => ({ matches: false }) }).chrome).toBe('ground-light')
  })

  it('carries the page grounds from the token file on one theme-color meta', () => {
    const metas = html.match(/<meta name="theme-color"[^>]*>/g) ?? []
    expect(metas).toHaveLength(1)
    expect(metas[0]).not.toContain('media=')
    const light = html.match(/<meta name="theme-color"[^>]*data-light="(#[0-9a-f]{6})"/)?.[1]
    const dark = html.match(/<meta name="theme-color"[^>]*data-dark="(#[0-9a-f]{6})"/)?.[1]
    const darkStart = tokens.indexOf(':root[data-theme="dark"]')
    expect(light).toBe(tokens.slice(0, darkStart).match(/--dl-bg:\s*(#[0-9a-f]{6})/)?.[1])
    expect(dark).toBe(tokens.slice(darkStart).match(/--dl-bg:\s*(#[0-9a-f]{6})/)?.[1])
  })
})
