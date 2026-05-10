/**
 * HeroStage tests — rotation, hover-pause, progress bar, ticker, keyword jump.
 *
 * Validates Requirements 1.3.1, 1.3.3, 1.3.6, 1.3.7, 1.3.8, 1.3.9, 1.3.10.
 *
 * All timing is driven via Vitest fake timers so the 7.5s cadence,
 * hover-pause math, and ticker reset behavior are deterministic without
 * sleeping the suite.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import HeroStage, { matchIntent } from './HeroStage'
import { INTENTS } from '../copy'

// HeroStage no longer reads `useUI()` — the SearchPill was removed in
// the storefront hero-drawer redesign. The mock below is kept for any
// remaining consumers in the test tree that render inside UIProvider.
// rotation / ticker behavior, not concierge wiring.
const mockOpenConciergeWithQuery = vi.fn()
vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({ openConciergeWithQuery: mockOpenConciergeWithQuery }),
}))

const CYCLE_MS = 7500

// Small helper so act() + timer advance always pair up - Testing Library
// needs this so React flushes state updates scheduled inside setInterval.
function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

beforeEach(() => {
  // `shouldAdvanceTime: false` keeps timers fully under test control. We
  // spike `Date.now()` via the built-in fake-timer clock so cycleStartRef
  // comparisons stay consistent with advanceTimersByTime.
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('HeroStage — intent rotation (Req 1.3.1)', () => {
  it('renders the first intent on mount', () => {
    render(<HeroStage />)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[0].query,
    )
  })

  it('advances to the second intent after 7.5s', () => {
    render(<HeroStage />)
    advance(CYCLE_MS + 100) // slight pad so the interval fires past the threshold
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[1].query,
    )
  })

  it('wraps back to the first intent after the 8th cycle', () => {
    render(<HeroStage />)
    // 8 full cycles should return us to index 0 (8 mod 8 = 0).
    advance((CYCLE_MS + 50) * INTENTS.length)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[0].query,
    )
  })
})

describe('HeroStage — productOverride for intent 2 (Req 1.3.3)', () => {
  it('renders the Featherweight Trail Runner when intent 2 is active', () => {
    render(<HeroStage />)
    // The image src/alt lag activeIndex by a 250ms crossfade midpoint
    // (see HeroStage.tsx: displayedIndex/setImageOpacity effect). Advance
    // one full cycle to flip activeIndex, then an additional beat so the
    // crossfade midpoint timer fires and displayedIndex catches up.
    advance(CYCLE_MS + 100)
    advance(300)
    // Intent 2 is `a thoughtful gift for someone who runs`.
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      'a thoughtful gift for someone who runs',
    )
    expect(screen.getByTestId('hero-image')).toHaveAttribute(
      'alt',
      'Featherweight Trail Runner',
    )
  })
})

describe('HeroStage — hover pauses rotation (Req 1.3.6)', () => {
  it('pauses rotation and freezes the progress bar while hovered', () => {
    render(<HeroStage />)
    const stage = screen.getByTestId('hero-stage')

    // Let ~40% of a cycle elapse then hover to freeze.
    advance(3000)
    const fillBefore = (screen.getByTestId('progress-bar-fill') as HTMLElement)
      .style.width

    act(() => {
      fireEvent.mouseEnter(stage)
    })

    // While hovered, advancing far past a full cycle must NOT change the
    // active intent and must NOT move the progress bar forward.
    advance(CYCLE_MS * 3)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[0].query,
    )
    const fillAfter = (screen.getByTestId('progress-bar-fill') as HTMLElement)
      .style.width
    expect(fillAfter).toBe(fillBefore)
    expect(stage).toHaveAttribute('data-hovering', 'true')
  })

  it('keeps ticker chips clickable while hovered', () => {
    render(<HeroStage />)
    const stage = screen.getByTestId('hero-stage')

    act(() => {
      fireEvent.mouseEnter(stage)
    })
    act(() => {
      fireEvent.click(screen.getByTestId('ticker-chip-3'))
    })

    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[3].query,
    )
  })
})

describe('HeroStage — unhover resumes from paused position (Req 1.3.7)', () => {
  it('resumes counting from where it paused (not from 0)', () => {
    render(<HeroStage />)
    const stage = screen.getByTestId('hero-stage')

    // Let ~2s of the 7.5s cycle pass (~26.6%), then hover.
    advance(2000)
    act(() => {
      fireEvent.mouseEnter(stage)
    })

    // Sit on hover for ten seconds - during real time this would have been
    // plenty to cycle forward.
    advance(10_000)

    // Unhover. Progress should continue from ~26.6%; the full cycle only
    // needs another ~5.5s to complete.
    act(() => {
      fireEvent.mouseLeave(stage)
    })

    // Still on the first intent (the cycle hasn't completed yet).
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[0].query,
    )

    // Another 5.5s brings us past the 7.5s total and advances to intent 2.
    advance(5_600)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[1].query,
    )
  })
})

describe('HeroStage — ticker click jumps and resets timer (Req 1.3.8)', () => {
  it('jumps to the clicked intent and resets the progress bar to 0', () => {
    render(<HeroStage />)

    // Let the cycle progress a bit first.
    advance(4000)

    act(() => {
      fireEvent.click(screen.getByTestId('ticker-chip-4'))
    })

    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[4].query,
    )
    // After the jump, the progress bar should be near 0% (first tick of the
    // new cycle lands within 60ms of the click).
    const fill = (screen.getByTestId('progress-bar-fill') as HTMLElement).style
      .width
    const pct = parseFloat(fill)
    expect(pct).toBeLessThan(5)
  })

  it('restarts the 7.5s timer from the jump so the NEXT advance is 7.5s later', () => {
    render(<HeroStage />)
    // Let some time pass so that without the reset, we'd be close to advancing.
    advance(6000)

    act(() => {
      fireEvent.click(screen.getByTestId('ticker-chip-2'))
    })

    // We jumped to intent 2. Advancing 6.5s would advance automatically
    // without a reset; with the reset, we stay on intent 2 (need full 7.5s).
    advance(6000)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[2].query,
    )

    // Another 1.6s crosses the 7.5s boundary and moves to intent 3.
    advance(1600)
    expect(screen.getByTestId('intent-query')).toHaveTextContent(
      INTENTS[3].query,
    )
  })
})

// SearchPill was removed in the storefront hero-drawer redesign.
// The keyword-match tests below are no longer applicable — the
// search pill is gone, replaced by the floating CommandPill + ⌘K
// shortcut + suggestion pills as drawer entry points.

describe('HeroStage — responsive breadcrumb (Req 1.3.10)', () => {
  it('renders the mobile-only dark glass breadcrumb marked hidden above md', () => {
    render(<HeroStage />)
    const breadcrumb = screen.getByTestId('mobile-breadcrumb')
    // Tailwind contract: visible at base, hidden at md+. jsdom can't compute
    // media queries, so we assert on the class contract the Header tests use.
    expect(breadcrumb).toHaveClass('md:hidden')
  })

  it('renders the desktop-only curated chip marked hidden below md', () => {
    render(<HeroStage />)
    const chip = screen.getByTestId('desktop-curated-chip')
    expect(chip).toHaveClass('hidden')
    expect(chip).toHaveClass('md:block')
  })
})

describe('matchIntent — keyword resolution helper', () => {
  it('matches against the intent query text', () => {
    expect(matchIntent('linen', INTENTS)).toBeGreaterThanOrEqual(0)
  })

  it('matches against the matchedOn tags', () => {
    // "footwear" appears in intent 2's matchedOn but not in the query text.
    const idx = matchIntent('footwear', INTENTS)
    expect(INTENTS[idx].matchedOn).toContain('footwear')
  })

  it('returns -1 on no match', () => {
    expect(matchIntent('zzzzzz', INTENTS)).toBe(-1)
  })

  it('ignores short connective tokens', () => {
    // "a" would match every query if short tokens were considered.
    expect(matchIntent('a', INTENTS)).toBe(-1)
  })
})
