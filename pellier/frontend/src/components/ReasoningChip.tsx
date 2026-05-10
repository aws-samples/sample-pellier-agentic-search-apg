/**
 * ReasoningChip — renders one of four rotating styles per product card.
 *
 * Validates Requirements 1.7.1, 1.7.2, 1.7.3, 1.7.4, 1.7.5.
 *
 * Four styles (keyed by `chip.style`):
 *
 *   - `picked`  — `Picked because {reason}` in italic Fraunces with a
 *                 small B mark prefix (Req 1.7.2). The `B` mark is a
 *                 circular cream dot with terracotta fill, echoing the
 *                 wordmark logo used elsewhere in the storefront.
 *
 *   - `matched` — `Matched on: {attr1} · {attr2} · {attr3}` in the
 *                 10px monospace footnote voice so it reads as a
 *                 quiet engineer-facing breadcrumb (Req 1.7.3). Copy
 *                 authoring lives in `copy.reasoningMatched`.
 *
 *   - `pricing` — two-part copy: the lead clause in the neutral Inter
 *                 body color, and a terracotta urgent clause that
 *                 wraps in `<span style={{color:'var(--accent)'}}>`
 *                 (Req 1.7.4). The urgent string is provided via
 *                 `chip.urgentClause`; it is rendered in the document
 *                 flow right after the lead with a single space so the
 *                 sentence reads naturally.
 *
 *   - `context` — free-form context copy authored by
 *                 `copy.reasoningContext` (Req 1.7.5). Renders in
 *                 italic Fraunces so it carries the editorial voice.
 *
 * Assignment helper:
 *   `assignReasoningChipsCyclic(inputs)` walks a list of `{ style,
 *   text, urgentClause }`-like inputs and rewrites the `style` field
 *   so that no two adjacent entries share a style when at least two
 *   distinct styles are available. The primary consumer is the
 *   9-card home-page grid (Req 1.7.1).
 */
import type { ReasoningChip as ReasoningChipModel } from '../services/types'

// --- Design tokens (storefront.md) ---------------------------------------
const CREAM = '#fbf4e8'
const ACCENT = '#c44536'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'

const INTER_STACK = 'Inter, system-ui, sans-serif'
const FRAUNCES_STACK = 'Fraunces, Georgia, serif'
const MONO_STACK =
  'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

interface ReasoningChipProps {
  chip: ReasoningChipModel
}

export default function ReasoningChip({ chip }: ReasoningChipProps) {
  const { style } = chip
  switch (style) {
    case 'picked':
      return <PickedChip chip={chip} />
    case 'matched':
      return <MatchedChip chip={chip} />
    case 'pricing':
      return <PricingChip chip={chip} />
    case 'context':
      return <ContextChip chip={chip} />
    default: {
      // Exhaustiveness guard — keeps new styles honest.
      const _never: never = style
      return <span data-testid="reasoning-chip" data-style={_never} />
    }
  }
}

// --- picked --------------------------------------------------------------

function PickedChip({ chip }: ReasoningChipProps) {
  return (
    <div
      data-testid="reasoning-chip"
      data-style="picked"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        color: INK_SOFT,
        fontFamily: FRAUNCES_STACK,
        fontStyle: 'italic',
        fontSize: 13,
        lineHeight: 1.45,
      }}
    >
      <BMark />
      <span>{chip.text}</span>
    </div>
  )
}

// --- matched -------------------------------------------------------------

function MatchedChip({ chip }: ReasoningChipProps) {
  return (
    <div
      data-testid="reasoning-chip"
      data-style="matched"
      style={{
        color: INK_QUIET,
        fontFamily: MONO_STACK,
        fontSize: 10,
        letterSpacing: '0.06em',
        lineHeight: 1.5,
      }}
    >
      <span>{chip.text}</span>
    </div>
  )
}

// --- pricing -------------------------------------------------------------

function PricingChip({ chip }: ReasoningChipProps) {
  const { text, urgentClause } = chip
  return (
    <div
      data-testid="reasoning-chip"
      data-style="pricing"
      style={{
        color: INK_SOFT,
        fontFamily: INTER_STACK,
        fontSize: 12,
        lineHeight: 1.5,
        letterSpacing: '0.01em',
      }}
    >
      <span>{text}</span>
      {urgentClause ? (
        <>
          {' '}
          <span
            data-testid="reasoning-chip-urgent"
            style={{ color: 'var(--accent)' }}
          >
            {urgentClause}
          </span>
        </>
      ) : null}
    </div>
  )
}

// --- context -------------------------------------------------------------

function ContextChip({ chip }: ReasoningChipProps) {
  return (
    <div
      data-testid="reasoning-chip"
      data-style="context"
      style={{
        color: INK_SOFT,
        fontFamily: FRAUNCES_STACK,
        fontStyle: 'italic',
        fontSize: 13,
        lineHeight: 1.45,
      }}
    >
      <span>{chip.text}</span>
    </div>
  )
}

// --- B mark avatar -------------------------------------------------------

function BMark() {
  return (
    <span
      aria-hidden
      data-testid="reasoning-chip-bmark"
      style={{
        display: 'inline-grid',
        placeItems: 'center',
        width: 16,
        height: 16,
        borderRadius: '50%',
        background: ACCENT,
        color: CREAM,
        fontFamily: FRAUNCES_STACK,
        fontStyle: 'italic',
        fontSize: 10,
        fontWeight: 600,
        lineHeight: 1,
        flexShrink: 0,
      }}
    >
      B
    </span>
  )
}

// --- Assignment helper (Req 1.7.1) --------------------------------------

/**
 * Returns a copy of `chips` whose `style` fields cycle through the
 * four rotating styles such that no two adjacent entries share a
 * style where possible. The input's `text` and `urgentClause` (if
 * any) are preserved; only the `style` label is rewritten.
 *
 * The algorithm is a simple greedy pass: at each index, pick the
 * next style from a cyclic iterator of the four canonical styles;
 * if that candidate collides with the previous entry, advance once
 * (guaranteed to resolve because we have 4 distinct styles). When
 * the caller provides fewer than two distinct styles to choose from
 * (degenerate case), adjacency cannot be avoided, so the function
 * preserves the declaration order without error.
 *
 * Intentionally deterministic so the 9-card home-page grid always
 * renders the same distribution for a given input length — tests can
 * assert the resulting style sequence exactly.
 */
export const CANONICAL_STYLES: ReasoningChipModel['style'][] = [
  'picked',
  'matched',
  'pricing',
  'context',
]

export function assignReasoningChipsCyclic(
  chips: ReasoningChipModel[],
): ReasoningChipModel[] {
  const cycle = CANONICAL_STYLES
  const result: ReasoningChipModel[] = []
  let cursor = 0

  for (let i = 0; i < chips.length; i += 1) {
    const prev = result[i - 1]?.style
    let style = cycle[cursor % cycle.length]
    if (style === prev) {
      cursor += 1
      style = cycle[cursor % cycle.length]
    }
    result.push({ ...chips[i], style })
    cursor += 1
  }

  return result
}

/**
 * Validates that a list of chips has no two adjacent entries sharing
 * a style. Handy for grid-level assertions; returns the first index
 * where adjacency is violated, or `-1` when the distribution is
 * clean.
 */
export function findAdjacentDuplicateStyleIndex(
  chips: ReasoningChipModel[],
): number {
  for (let i = 1; i < chips.length; i += 1) {
    if (chips[i].style === chips[i - 1].style) return i
  }
  return -1
}
