/**
 * SectionEyebrow contract.
 *
 * The whole point of the primitive is that one recipe replaces five, so the
 * recipe itself is what is asserted: sans, 13px, 600, sentence case. A
 * snapshot would pass while someone quietly moved it to mono at 10px, which is
 * exactly the drift this component exists to end.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SectionEyebrow } from './SectionEyebrow'

describe('SectionEyebrow', () => {
  it('renders the one recipe: sans 13/600 in sentence case', () => {
    render(<SectionEyebrow data-testid="eyebrow">Reference views</SectionEyebrow>)

    const eyebrow = screen.getByTestId('eyebrow')
    expect(eyebrow).toHaveStyle({
      fontFamily: 'var(--obs-heading)',
      fontSize: '13px',
      fontWeight: '600',
    })
    expect(eyebrow.style.textTransform).toBe('')
  })

  it('never renders in the monospace register', () => {
    // Mono on these surfaces means "identifier, table, duration". A section
    // label is none of those, and spending mono on labels is what left the
    // real identifiers with nothing to distinguish them.
    render(<SectionEyebrow data-testid="eyebrow">Namespace pattern</SectionEyebrow>)

    const style = screen.getByTestId('eyebrow').getAttribute('style') ?? ''
    expect(style).not.toMatch(/mono/)
  })

  it('separates the two tones by colour and reports which one it used', () => {
    const { unmount } = render(
      <SectionEyebrow data-testid="brand">Evidence</SectionEyebrow>,
    )
    const brand = screen.getByTestId('brand')
    expect(brand).toHaveAttribute('data-tone', 'brand')
    expect(brand).toHaveStyle({ color: 'var(--obs-ink-2)' })
    // Burgundy is the mark, not the text: it stays on the dot only.
    const dot = brand.querySelector('[aria-hidden="true"]') as HTMLElement
    expect(dot.style.background).toBe('var(--pellier-accent)')
    unmount()

    render(
      <SectionEyebrow tone="muted" data-testid="muted">
        Evidence
      </SectionEyebrow>,
    )
    const muted = screen.getByTestId('muted')
    expect(muted).toHaveAttribute('data-tone', 'muted')
    // ink-3, not ink-4: at 13px, ink-4 on the cream card measured 3.85:1 against
    // the 4.5:1 floor (axe, /observatory/architecture/runtime).
    expect(muted).toHaveStyle({ color: 'var(--obs-ink-3)' })
  })

  it('hides the dot from assistive technology and can drop it entirely', () => {
    const { container, unmount } = render(
      <SectionEyebrow>What ran?</SectionEyebrow>,
    )
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1)
    unmount()

    const { container: noDot } = render(
      <SectionEyebrow dot={false}>What ran?</SectionEyebrow>,
    )
    expect(noDot.querySelectorAll('[aria-hidden="true"]')).toHaveLength(0)
  })

  it('keeps the label readable as text, not as an image of text', () => {
    render(<SectionEyebrow data-testid="eyebrow">Reference views</SectionEyebrow>)
    // Uppercase is presentational: the accessible text stays as authored.
    expect(screen.getByTestId('eyebrow')).toHaveTextContent('Reference views')
  })
})
