/**
 * OperatorState tests.
 *
 * Ten desk states used to be ten hand-written grey boxes. What is worth
 * pinning about the replacement is not how it looks but which of them earns
 * the photograph, that the photograph is loaded through the asset helpers so
 * it survives the Workshop Studio base path, and that the identifier an
 * operator would go and check is still on the page.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import OperatorState from './OperatorState'

describe('OperatorState', () => {
  it('names the panel, the absence, the cause and the identifier', () => {
    render(
      <OperatorState
        data-testid="operator-book-empty"
        eyebrow="Clients"
        headline="No clients seeded"
        body="Apply the migration to seed the book."
        reason="client_book_empty"
      />,
    )

    const state = screen.getByTestId('operator-book-empty')
    expect(state).toHaveTextContent('Clients')
    expect(state).toHaveTextContent('No clients seeded')
    expect(state).toHaveTextContent('Apply the migration to seed the book.')
    expect(state).toHaveTextContent('client_book_empty')
  })

  it('sets the absence in the display face, as a heading', () => {
    render(
      <OperatorState
        level={1}
        data-testid="operator-book-empty"
        eyebrow="Clients"
        headline="No clients seeded"
      />,
    )

    // Every one of these states replaces the whole page, so each is that
    // page's h1. The desk's signed-out state is the case that mattered:
    // rendered as a paragraph it left `/operator` with no headings at all,
    // which is the first thing an unauthenticated operator meets. The desk
    // sets it in its own heading voice, Instrument Sans at 600.
    const headline = screen.getByRole('heading', { level: 1 })
    expect(headline).toHaveTextContent('No clients seeded')
    expect(headline).toHaveStyle({ fontFamily: 'var(--sans)', fontWeight: '600' })
  })

  it('rests on paper by default and carries no photograph', () => {
    const { container } = render(
      <OperatorState
        data-testid="operator-reviews-empty"
        eyebrow="Action queue"
        headline="No actions waiting"
      />,
    )

    expect(screen.getByTestId('operator-reviews-empty')).toHaveAttribute(
      'data-surface',
      'paper',
    )
    expect(container.querySelector('img')).toBeNull()
  })

  it('shows the house plate for the one state that is not a failure', () => {
    const { container } = render(
      <OperatorState
        data-testid="operator-book-error"
        surface="plate"
        eyebrow="Clients"
        headline="Operator sign-in required"
      />,
    )

    expect(screen.getByTestId('operator-book-error')).toHaveAttribute(
      'data-surface',
      'plate',
    )

    // Through imageSrc()/responsiveImageSrcSet(), never a CSS url(): a bare
    // root-relative path 404s behind the Workshop Studio /ports/8000/ proxy.
    const img = container.querySelector('img')
    expect(img?.getAttribute('src')).toContain('/products/hero-fresh-2-960.webp')
    expect(
      container.querySelector('source[type="image/avif"]')?.getAttribute('srcSet'),
    ).toContain('/products/hero-fresh-2-1600.avif')

    // Decorative: the state's own words carry the meaning.
    expect(img).toHaveAttribute('alt', '')
    expect(img).toHaveAttribute('aria-hidden', 'true')
  })

  it('renders the lead link above the state and at most one action', () => {
    render(
      <OperatorState
        data-testid="operator-record-error"
        eyebrow="Client record"
        headline="Record unavailable"
        lead={<a href="/operator">Clients</a>}
        action={<button type="button">Sign in</button>}
      />,
    )

    const state = screen.getByTestId('operator-record-error')
    expect(state.querySelector('.operator-state-lead')).not.toBeNull()
    expect(screen.getByRole('link', { name: 'Clients' })).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })
})

/**
 * vitest runs with `css: false`, so the two rules the contrast figures depend
 * on are unreachable through the DOM. They are read from the stylesheet the
 * way `governed_tokens_import.test.ts` reads its contract.
 */
describe('the plate scrim, as a stylesheet contract', () => {
  const css = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../styles/operator.css'),
    'utf8',
  )

  it('paints the scrim after the photograph, not before it', () => {
    // A `::before` is generated as the element's FIRST child, so at equal
    // stacking level the plate that follows it in the DOM paints on top and
    // the scrim does nothing at all. That shipped once and looked like a weak
    // gradient rather than an inert one.
    expect(css).toContain(".operator-state[data-surface='plate']::after")
    expect(css).toContain('.operator-record-head::after')
    expect(css).not.toContain(".operator-state[data-surface='plate']::before")
    expect(css).not.toContain('.operator-record-head::before')
  })

  it('keeps the espresso scrim at or above the measured 0.70 floor', () => {
    // 0.70 over the brightest pixel in the plates resolves to #625a56: cream
    // reads 6.3:1 and --op-band-muted 4.6:1. Below it the muted tone fails AA.
    const floors = css.match(/rgb\(31 20 16 \/ 0\.7\)/g) ?? []
    expect(floors.length).toBeGreaterThanOrEqual(2)
  })
})
