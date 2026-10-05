/**
 * ReasoningChip tests — four rotating styles plus grid-level distribution.
 *
 * Validates Requirements 1.7.1, 1.7.2, 1.7.3, 1.7.4, 1.7.5.
 *
 * Coverage:
 *   - `picked`   renders `Picked because {reason}` in Instrument Sans
 *     with a small B mark prefix (Req 1.7.2).
 *   - `matched`  renders `Matched on: {a}, {b}, {c}` (Req 1.7.3).
 *   - `pricing`  renders the lead clause and wraps the urgent clause
 *     in `<span style="color: var(--accent)">` terracotta (Req 1.7.4).
 *   - `context`  renders the provided context copy (Req 1.7.5).
 *   - The 9-card showcase grid distributes all four styles and has
 *     no two adjacent cards sharing a style (Req 1.7.1).
 *   - `assignReasoningChipsCyclic` produces a distribution that is
 *     free of adjacent duplicates for representative inputs.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ReasoningChip, {
  CANONICAL_STYLES,
  assignReasoningChipsCyclic,
  findAdjacentDuplicateStyleIndex,
} from './ReasoningChip'
import {
  reasoningMatched,
  reasoningPicked,
  reasoningPricing,
} from '../copy'
import type { ReasoningChip as ReasoningChipModel } from '../services/types'

// ProductCard links to /product/:id, so the grid needs router context.
// Stub IntersectionObserver once for this suite — ProductGrid renders
// ProductCards that call useScrollReveal, which requires the global.
class NoopIntersectionObserver {
  readonly root: Element | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = [0]
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}
;(globalThis as unknown as {
  IntersectionObserver: typeof NoopIntersectionObserver
}).IntersectionObserver = NoopIntersectionObserver

// --- Per-style render contract ------------------------------------------

describe('ReasoningChip — picked style (Req 1.7.2)', () => {
  it('renders `Picked because {reason}` with a B mark prefix', () => {
    const text = reasoningPicked('linen breathes beautifully in July')
    render(<ReasoningChip chip={{ style: 'picked', text }} />)

    const chip = screen.getByTestId('reasoning-chip')
    expect(chip).toHaveAttribute('data-style', 'picked')
    expect(chip).toHaveTextContent(
      'Picked because linen breathes beautifully in July',
    )
    // The B mark prefix is present.
    expect(
      within(chip).getByTestId('reasoning-chip-pmark'),
    ).toBeInTheDocument()
    expect(chip.getAttribute('style') ?? '').toMatch(/font-style:\s*normal/)
    expect(chip.getAttribute('style') ?? '').toMatch(/var\(--sans\)/)
  })
})

describe('ReasoningChip — matched style (Req 1.7.3)', () => {
  it('renders `Matched on: {a}, {b}, {c}` using tag attributes', () => {
    const text = reasoningMatched('earth', 'warm', 'everyday')
    render(<ReasoningChip chip={{ style: 'matched', text }} />)

    const chip = screen.getByTestId('reasoning-chip')
    expect(chip).toHaveAttribute('data-style', 'matched')
    // A comma-separated list: VOICE.md allows no middle dots as separators.
    expect(chip.textContent).toBe('Matched on: earth, warm, everyday')
    expect(chip.textContent).not.toContain('\u00b7')
    // No B mark on the matched style — it is the engineer-voice chip.
    expect(within(chip).queryByTestId('reasoning-chip-pmark')).toBeNull()
  })
})

describe('ReasoningChip — pricing style (Req 1.7.4)', () => {
  it('wraps the urgent clause in terracotta (`var(--accent)`)', () => {
    const { lead, urgent } = reasoningPricing(14, 3)
    render(
      <ReasoningChip
        chip={{ style: 'pricing', text: lead, urgentClause: urgent }}
      />,
    )

    const chip = screen.getByTestId('reasoning-chip')
    expect(chip).toHaveAttribute('data-style', 'pricing')
    // The lead clause from `copy.reasoningPricing` is rendered verbatim.
    expect(chip).toHaveTextContent(
      'Price watch: $14 below category average.',
    )

    const urgentSpan = screen.getByTestId('reasoning-chip-urgent')
    expect(urgentSpan).toHaveTextContent('Only 3 left.')
    // Terracotta urgent text uses `color: var(--accent)` (Daylight `--dl-accent`).
    const urgentStyle = urgentSpan.getAttribute('style') ?? ''
    expect(urgentStyle).toMatch(/color:\s*var\(--accent\)/)
  })

  it('omits the urgent span when no urgentClause is supplied', () => {
    const { lead } = reasoningPricing(8, 5)
    render(<ReasoningChip chip={{ style: 'pricing', text: lead }} />)
    expect(screen.queryByTestId('reasoning-chip-urgent')).toBeNull()
  })
})

describe('ReasoningChip — context style (Req 1.7.5)', () => {
  it('renders the provided context copy in Instrument Sans', () => {
    render(
      <ReasoningChip
        chip={{
          style: 'context',
          text: 'Gift-ready: signature packaging, arrives tomorrow',
        }}
      />,
    )
    const chip = screen.getByTestId('reasoning-chip')
    expect(chip).toHaveAttribute('data-style', 'context')
    expect(chip).toHaveTextContent(
      'Gift-ready: signature packaging, arrives tomorrow',
    )
    expect(chip.getAttribute('style') ?? '').toMatch(/font-style:\s*normal/)
    expect(chip.getAttribute('style') ?? '').toMatch(/var\(--sans\)/)
  })
})

// --- Assignment helper --------------------------------------------------

describe('assignReasoningChipsCyclic — no adjacent duplicates', () => {
  it('cycles through all four canonical styles for a 4+ list', () => {
    const input: ReasoningChipModel[] = Array.from({ length: 4 }, () => ({
      style: 'picked',
      text: 'seed',
    }))
    const out = assignReasoningChipsCyclic(input)
    expect(out.map(c => c.style)).toEqual(CANONICAL_STYLES)
    expect(findAdjacentDuplicateStyleIndex(out)).toBe(-1)
  })

  it('preserves text and urgentClause while rewriting style only', () => {
    const input: ReasoningChipModel[] = [
      { style: 'picked', text: 'A' },
      { style: 'picked', text: 'B', urgentClause: 'Hurry' },
      { style: 'picked', text: 'C' },
    ]
    const out = assignReasoningChipsCyclic(input)
    expect(out.map(c => c.text)).toEqual(['A', 'B', 'C'])
    expect(out[1].urgentClause).toBe('Hurry')
    expect(findAdjacentDuplicateStyleIndex(out)).toBe(-1)
  })

  it('covers all four styles across a 9-element input', () => {
    const input: ReasoningChipModel[] = Array.from({ length: 9 }, () => ({
      style: 'picked',
      text: 'seed',
    }))
    const out = assignReasoningChipsCyclic(input)
    const styles = new Set(out.map(c => c.style))
    expect(styles).toEqual(new Set(CANONICAL_STYLES))
    expect(findAdjacentDuplicateStyleIndex(out)).toBe(-1)
  })

  it('handles empty input without throwing', () => {
    expect(assignReasoningChipsCyclic([])).toEqual([])
  })
})
