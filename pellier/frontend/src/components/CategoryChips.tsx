/**
 * CategoryChips — the horizontal category filter row beneath the status strip.
 *
 * Validates Requirements 1.5.3 and 1.5.4.
 *
 * Renders the 7 chips from `copy.ts` in the order:
 *   All (dusk fill, selected by default), Linen, Dresses, Accessories,
 *   Outerwear, Footwear, Home.
 *
 * Behavior:
 *   - Single-select. Clicking a chip sets it as the new selection; clicking
 *     "All" clears any active category filter (treated as "no category").
 *   - The component is controlled when `selected` is provided so parent
 *     state (e.g., a router query param) is the source of truth. When left
 *     uncontrolled it manages its own internal state starting at `All`.
 *   - Emits the selected chip label via `onChange`. The parent is
 *     responsible for passing the label to `/api/products` as a
 *     `?category=<name>` query param (per task 4.5).
 */
import { useCallback, useMemo, useState } from 'react'
import { CATEGORY_CHIPS } from '../copy'

// --- Design tokens (storefront.md) --------------------------------------
const CREAM = '#fbf4e8'
const CREAM_WARM = '#f5e8d3'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const INK_QUIET = '#a68668'
const DUSK = '#3d2518'

// The "no category" label doubles as the default selection (Req 1.5.3).
export const ALL_CATEGORY = 'All'

// Exported union-ish type so callers can safely narrow before hitting the API.
export type CategoryLabel = (typeof CATEGORY_CHIPS)[number]

interface CategoryChipsProps {
  /**
   * Optional controlled selection. When omitted the component starts at
   * `All` and manages its own state. `null` is treated the same as `All`.
   */
  selected?: CategoryLabel | null
  /**
   * Fires after a click. `All` is reported as the literal string so parents
   * can pass it straight through a router without branching.
   */
  onChange?: (next: CategoryLabel) => void
}

export default function CategoryChips({
  selected,
  onChange,
}: CategoryChipsProps) {
  // Controlled-or-uncontrolled: mirror the React `<input value={...}>`
  // convention so the component is useful both ways.
  const [internal, setInternal] = useState<CategoryLabel>(ALL_CATEGORY)
  const effective: CategoryLabel = useMemo(() => {
    if (selected === undefined) return internal
    return selected ?? ALL_CATEGORY
  }, [selected, internal])

  const handleClick = useCallback(
    (label: CategoryLabel) => {
      if (selected === undefined) setInternal(label)
      onChange?.(label)
    },
    [selected, onChange],
  )

  return (
    <nav
      data-testid="category-chips"
      aria-label="Filter products by category"
      className="w-full"
      style={{
        background: CREAM,
        padding: '12px 24px',
      }}
    >
      <ul
        className="mx-auto flex max-w-6xl items-center gap-2 overflow-x-auto whitespace-nowrap"
        style={{ listStyle: 'none', margin: 0, padding: 0 }}
      >
        <li className="flex-shrink-0">
          <span
            data-testid="category-chips-eyebrow"
            style={{
              color: INK_QUIET,
              fontSize: '10px',
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              fontWeight: 600,
              paddingRight: '6px',
            }}
          >
            Explore
          </span>
        </li>
        {CATEGORY_CHIPS.map(label => {
          const isActive = effective === label
          return (
            <li key={label}>
              <button
                type="button"
                data-testid={`category-chip-${label.toLowerCase()}`}
                data-active={isActive ? 'true' : 'false'}
                aria-pressed={isActive}
                onClick={() => handleClick(label)}
                className="rounded-full transition-colors"
                style={{
                  background: isActive ? DUSK : CREAM_WARM,
                  color: isActive ? CREAM : INK_SOFT,
                  border: `1px solid ${isActive ? DUSK : 'rgba(45, 24, 16, 0.08)'}`,
                  padding: '8px 18px',
                  fontSize: '13px',
                  letterSpacing: '0.04em',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    const btn = e.currentTarget as HTMLButtonElement
                    btn.style.color = INK
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    const btn = e.currentTarget as HTMLButtonElement
                    btn.style.color = INK_SOFT
                  }
                }}
              >
                {label}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
