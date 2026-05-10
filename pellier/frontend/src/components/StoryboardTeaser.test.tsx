/**
 * StoryboardTeaser tests - 3-card editorial grid.
 *
 * Validates Requirements 1.9.1, 1.9.2, 1.9.3, 1.9.4.
 *
 * Coverage:
 *   - Always renders exactly 3 cards (Req 1.9.1). "Never 1" is the
 *     explicit done-when from task 4.8.
 *   - Each card renders the image, category badge, volume number,
 *     theme, italic Fraunces title, excerpt, and terracotta
 *     `Read the full vision \u203a` link (Req 1.9.2, 1.9.4).
 *   - Hovering a card scales its image `transform` to `scale(1.05)`
 *     (Req 1.9.3).
 *   - The three cards render in the exact authored order:
 *     `MOOD FILM \u00b7 Vol. 12 \u00b7 Summer`,
 *     `VISION BOARD \u00b7 Vol. 11 \u00b7 The Makers`,
 *     `BEHIND THE SCENES \u00b7 Vol. 10 \u00b7 The Edit` (Req 1.9.4).
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StoryboardTeaser from './StoryboardTeaser'
import { STORYBOARD_TEASERS } from '../copy'

describe('StoryboardTeaser - 3-card grid (Req 1.9.1)', () => {
  it('renders exactly 3 cards, never 1', () => {
    render(<StoryboardTeaser />)
    const cards = screen.getAllByRole('listitem')
    expect(cards).toHaveLength(3)
  })

  it('renders each card from the authored STORYBOARD_TEASERS order', () => {
    render(<StoryboardTeaser />)

    // The data source must carry exactly three authored cards; the
    // component should not pad or drop entries.
    expect(STORYBOARD_TEASERS).toHaveLength(3)
    for (let i = 0; i < STORYBOARD_TEASERS.length; i += 1) {
      expect(screen.getByTestId(`storyboard-card-${i}`)).toBeInTheDocument()
    }
  })
})

describe('StoryboardTeaser - per-card contents (Req 1.9.2, 1.9.4)', () => {
  it('renders the three cards with the exact eyebrow lines from the spec', () => {
    render(<StoryboardTeaser />)

    expect(screen.getByTestId('storyboard-card-eyebrow-0')).toHaveTextContent(
      'MOOD FILM \u00b7 Vol. 12 \u00b7 Summer',
    )
    expect(screen.getByTestId('storyboard-card-eyebrow-1')).toHaveTextContent(
      'VISION BOARD \u00b7 Vol. 11 \u00b7 The Makers',
    )
    expect(screen.getByTestId('storyboard-card-eyebrow-2')).toHaveTextContent(
      'BEHIND THE SCENES \u00b7 Vol. 10 \u00b7 The Edit',
    )
  })

  it('renders the title, excerpt, and link for each card verbatim from copy.ts', () => {
    render(<StoryboardTeaser />)

    STORYBOARD_TEASERS.forEach((card, i) => {
      const root = screen.getByTestId(`storyboard-card-${i}`)
      expect(within(root).getByTestId(`storyboard-card-title-${i}`)).toHaveTextContent(
        card.title,
      )
      expect(within(root).getByTestId(`storyboard-card-excerpt-${i}`)).toHaveTextContent(
        card.excerpt,
      )
      expect(within(root).getByTestId(`storyboard-card-link-${i}`)).toHaveTextContent(
        card.link,
      )
    })
  })

  it('renders an editorial image with the golden wash overlay per card', () => {
    render(<StoryboardTeaser />)

    STORYBOARD_TEASERS.forEach((card, i) => {
      const img = screen.getByTestId(
        `storyboard-card-image-${i}`,
      ) as HTMLImageElement
      expect(img.getAttribute('src')).toBe(card.imageUrl)
      expect(img.getAttribute('alt')).toBe(card.imageAlt)
      expect(screen.getByTestId(`storyboard-card-wash-${i}`)).toBeInTheDocument()
    })
  })

  it('renders titles in italic Fraunces', () => {
    render(<StoryboardTeaser />)
    for (let i = 0; i < STORYBOARD_TEASERS.length; i += 1) {
      const title = screen.getByTestId(`storyboard-card-title-${i}`)
      const style = title.getAttribute('style') ?? ''
      expect(style).toMatch(/font-style:\s*italic/)
      expect(style).toMatch(/Fraunces/)
    }
  })

  it('renders each "Read the full vision" link in terracotta (var(--accent))', () => {
    render(<StoryboardTeaser />)
    for (let i = 0; i < STORYBOARD_TEASERS.length; i += 1) {
      const link = screen.getByTestId(`storyboard-card-link-${i}`)
      const style = link.getAttribute('style') ?? ''
      // `#c44536` is the design-token value of `--accent` from storefront.md.
      // jsdom normalizes hex colors to `rgb(...)` form, so accept either
      // the raw token, the hex, or the normalized rgb triplet.
      expect(style).toMatch(
        /color:\s*(var\(--accent\)|#c44536|rgb\(\s*196,\s*69,\s*54\s*\))/,
      )
    }
  })
})

describe('StoryboardTeaser - hover scale (Req 1.9.3)', () => {
  it('scales the image to 1.05 on mouse enter and resets on mouse leave', () => {
    render(<StoryboardTeaser />)

    const card = screen.getByTestId('storyboard-card-0')
    const img = screen.getByTestId('storyboard-card-image-0')

    // Pre-hover: image is at its resting scale.
    expect(img.getAttribute('style') ?? '').toMatch(/transform:\s*scale\(1\)/)
    expect(card).toHaveAttribute('data-hovered', 'false')

    fireEvent.mouseEnter(card)
    expect(img.getAttribute('style') ?? '').toMatch(
      /transform:\s*scale\(1\.05\)/,
    )
    expect(card).toHaveAttribute('data-hovered', 'true')

    fireEvent.mouseLeave(card)
    expect(img.getAttribute('style') ?? '').toMatch(/transform:\s*scale\(1\)/)
    expect(card).toHaveAttribute('data-hovered', 'false')
  })
})
