/**
 * The pellier. wordmark: the original app's lockup, exactly. Fraunces 400 at
 * -1.8px, 31px in the header and 36px in the footer, with the copper dot in
 * both themes. Vitest runs with CSS off, so the token contract is read from
 * the stylesheets directly.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import Wordmark from './Wordmark'

const here = dirname(fileURLToPath(import.meta.url))
const tokens = readFileSync(resolve(here, '../styles/daylight-tokens.css'), 'utf8')
const landing = readFileSync(resolve(here, '../styles/pellier-landing.css'), 'utf8')
const nav = readFileSync(resolve(here, '../styles/surface-navigation.css'), 'utf8')

function block(css: string, selector: string): string {
  const start = css.indexOf(selector)
  if (start < 0) throw new Error(`${selector} not found`)
  const open = css.indexOf('{', start)
  const close = css.indexOf('}', open)
  return css.slice(open, close)
}

describe('Wordmark', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
  })

  it.each(['light', 'dark'])('renders pellier with the copper dot in the %s theme', (theme) => {
    document.documentElement.setAttribute('data-theme', theme)
    render(<MemoryRouter><Wordmark /></MemoryRouter>)

    const mark = screen.getByRole('link', { name: 'Pellier home' })
    expect(mark).toHaveClass('pellier-brand')
    expect(mark).toHaveTextContent('pellier.')
    const dot = mark.querySelector('.pellier-brand-dot')
    expect(dot).not.toBeNull()
    expect(dot).toHaveTextContent('.')
    expect(mark).toHaveAttribute('href', '/')
  })

  it('switches the dot between the light and dark copper through one token', () => {
    expect(block(nav, '.pellier-brand-dot')).toContain('color: var(--pellier-copper)')
    expect(landing).toMatch(/--pellier-copper:\s*var\(--dl-accent\)/)
    const light = tokens.slice(0, tokens.indexOf(':root[data-theme="dark"]'))
    const dark = tokens.slice(tokens.indexOf(':root[data-theme="dark"]'))
    expect(light).toMatch(/--dl-accent:\s*#9a4d20/)
    expect(dark).toMatch(/--dl-accent:\s*#da9562/)
    expect(light).toMatch(/--dl-ink:\s*#111110/)
    expect(dark).toMatch(/--dl-ink:\s*#f3ebe2/)
  })

  it('is the only element set in Fraunces, at the original sizes', () => {
    const brand = block(nav, '.pellier-brand {')
    expect(brand).toContain('font-family: var(--dl-font-display)')
    expect(brand).toContain('font-size: 31px')
    expect(brand).toContain('font-weight: 400')
    expect(brand).toContain('letter-spacing: -1.8px')
    expect(block(nav, '.pellier-brand-footer')).toContain('font-size: 36px')
    render(<MemoryRouter><Wordmark size="footer" /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Pellier home' })).toHaveClass('pellier-brand-footer')
  })
})
