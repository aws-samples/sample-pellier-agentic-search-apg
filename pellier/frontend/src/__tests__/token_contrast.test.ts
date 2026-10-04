/**
 * AA contrast or better for text and controls in both themes, computed from
 * the token file itself so a value change that breaks a pair fails here.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(here, '../styles/daylight-tokens.css'), 'utf8')

function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const match of block.matchAll(/(--dl-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[match[1]] = match[2]
  return out
}

const darkStart = css.indexOf(':root[data-theme="dark"]')
const LIGHT = tokens(css.slice(0, darkStart))
const DARK = { ...LIGHT, ...tokens(css.slice(darkStart)) }

function luminance(hex: string): number {
  const channel = (c: number) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  const n = parseInt(hex.slice(1), 16)
  return 0.2126 * channel(n >> 16) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** Text on each ground it is set on. */
const TEXT_PAIRS: Array<[string, string]> = [
  ['--dl-ink', '--dl-bg'], ['--dl-ink-2', '--dl-bg'], ['--dl-muted', '--dl-bg'], ['--dl-faint', '--dl-bg'],
  ['--dl-ink', '--dl-dock'], ['--dl-ink-2', '--dl-dock'], ['--dl-muted', '--dl-dock'],
  ['--dl-ink', '--dl-paper'], ['--dl-ink-2', '--dl-paper'], ['--dl-muted', '--dl-paper'],
  ['--dl-ink', '--dl-paper-2'], ['--dl-ink-2', '--dl-paper-2'], ['--dl-muted', '--dl-paper-2'],
  ['--dl-accent', '--dl-bg'], ['--dl-accent', '--dl-dock'], ['--dl-accent', '--dl-paper-2'],
  ['--dl-accent-ink', '--dl-accent-soft'],
  ['--dl-on-ink', '--dl-ink'],
  ['--dl-ok', '--dl-bg'], ['--dl-ok', '--dl-ok-soft'],
  ['--dl-err', '--dl-bg'], ['--dl-err', '--dl-err-soft'],
  ['--dl-warn', '--dl-bg'],
  ['--dl-tag-good-ink', '--dl-tag-good-bg'],
  ['--dl-tag-blocked-ink', '--dl-tag-blocked-bg'],
  ['--dl-accent-on-ink', '--dl-ink'],
]

describe.each([['light', LIGHT], ['dark', DARK]] as const)('%s theme contrast', (_name, theme) => {
  it.each(TEXT_PAIRS)('%s on %s is AA (4.5:1) or better', (fg, bg) => {
    expect(theme[fg], fg).toBeDefined()
    expect(theme[bg], bg).toBeDefined()
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5)
  })

  it('keeps the page ground as the brief states it', () => {
    expect(theme['--dl-bg']).toBe(_name === 'light' ? '#ffffff' : '#000000')
  })
})
