/**
 * AA contrast or better for text, and 3:1 or better for controls and
 * marks, in both themes, computed from the token file itself so a value
 * change that breaks a pair fails here.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(here, '../styles/daylight-tokens.css'), 'utf8')
/* The persona initial sits on the color each persona is seeded with. */
const seed = readFileSync(
  resolve(here, '../../../../scripts/migrations/029_live_surface_data.sql'),
  'utf8',
)
/* The static theme-color meta the inline script picks from before paint. */
const indexHtml = readFileSync(resolve(here, '../../index.html'), 'utf8')

function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const match of block.matchAll(/(--dl-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[match[1]] = match[2]
  return out
}

const darkStart = css.indexOf(':root[data-theme="dark"]')
const LIGHT = tokens(css.slice(0, darkStart))
const DARK = { ...LIGHT, ...tokens(css.slice(darkStart)) }

/* `'#5a3528', 'M',`: the avatar color precedes the avatar initial. */
const SEEDED_AVATAR_COLORS = Array.from(
  seed.matchAll(/'(#[0-9a-fA-F]{6})',\s*'[A-Z]',/g),
  (match) => match[1],
)

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

/** Text on each ground it is set on: AA, 4.5:1. */
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

/**
 * Controls and marks that are not text (WCAG 1.4.11, 3:1): the copper dot on
 * the ink-filled Ask Pellier button at rest and on its hover ground, and the
 * dot on the ink p. mark. The dot is the other theme's copper for exactly
 * this reason; the theme's own copper measured 3.11:1 light and 2.10:1 dark.
 */
const CONTROL_PAIRS: Array<[string, string]> = [
  ['--dl-accent-on-ink', '--dl-ink'],
  ['--dl-accent-on-ink', '--dl-ink-2'],
]

describe.each([['light', LIGHT], ['dark', DARK]] as const)('%s theme contrast', (_name, theme) => {
  it.each(TEXT_PAIRS)('%s on %s is AA (4.5:1) or better', (fg, bg) => {
    expect(theme[fg], fg).toBeDefined()
    expect(theme[bg], bg).toBeDefined()
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5)
  })

  it.each(CONTROL_PAIRS)('the dot %s on %s is 3:1 or better', (fg, bg) => {
    expect(theme[fg], fg).toBeDefined()
    expect(theme[bg], bg).toBeDefined()
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3)
  })

  it('keeps the persona initial readable on every seeded avatar color', () => {
    expect(SEEDED_AVATAR_COLORS.length).toBeGreaterThanOrEqual(3)
    for (const ground of SEEDED_AVATAR_COLORS) {
      expect(contrast(theme['--dl-on-photo'], ground), ground).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('keeps the page ground as the brief states it', () => {
    expect(theme['--dl-bg']).toBe(_name === 'light' ? '#ffffff' : '#000000')
  })
})

/**
 * Hairlines on the black grounds stay visible (1.25:1): the hairline on the
 * page, the dock and a panel, and the strong line on a recessed field, where
 * the hairline itself measures 1.15:1. Light keeps the owner's hairline,
 * #e9e9e5, which reads 1.22:1 on white, so this check is dark only.
 */
const DARK_RULE_PAIRS: Array<[string, string]> = [
  ['--dl-line', '--dl-bg'], ['--dl-line', '--dl-dock'], ['--dl-line', '--dl-paper'],
  ['--dl-line-strong', '--dl-paper-2'],
]

describe('dark rules', () => {
  it.each(DARK_RULE_PAIRS)('%s on %s is 1.25:1 or better', (fg, bg) => {
    expect(contrast(DARK[fg], DARK[bg])).toBeGreaterThanOrEqual(1.25)
  })
})

describe('the browser chrome', () => {
  it('takes the page ground in each theme, before and after paint', () => {
    const meta = indexHtml.match(/<meta\s+name="theme-color"[^>]*>/)?.[0] ?? ''
    const attr = (name: string) => meta.match(new RegExp(`${name}="(#[0-9a-fA-F]{6})"`))?.[1]
    expect(attr('data-light')).toBe(LIGHT['--dl-bg'])
    expect(attr('data-dark')).toBe(DARK['--dl-bg'])
    expect(attr('content')).toBe(LIGHT['--dl-bg'])
  })
})

describe('the brand-mark ground', () => {
  /* Payment marks keep their own colors and are drawn for white; a ground
     within a step of white keeps every one of them as legible as on white. */
  it.each([['light', LIGHT], ['dark', DARK]] as const)('stays within a step of white in the %s theme', (_name, theme) => {
    expect(theme['--dl-mark-ground']).toBeDefined()
    expect(contrast(theme['--dl-mark-ground'], '#ffffff')).toBeLessThanOrEqual(1.2)
  })
})

describe('the theme-independent values', () => {
  it('on-photo is the same ivory in both themes, so it reads on a seeded color either way', () => {
    expect(LIGHT['--dl-on-photo']).toBe(DARK['--dl-on-photo'])
  })

  it('the accent on ink is the other theme\'s copper', () => {
    expect(LIGHT['--dl-accent-on-ink']).toBe(DARK['--dl-accent'])
    expect(DARK['--dl-accent-on-ink']).toBe(LIGHT['--dl-accent'])
  })
})
