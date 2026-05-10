/**
 * CategoryChips tests — horizontal category filter row.
 *
 * Validates Requirements 1.5.3 and 1.5.4.
 *
 * Coverage:
 *   - Renders exactly the 7 chips from copy.ts in the documented order
 *     (Req 1.5.3).
 *   - `All` is selected by default and carries the dusk-fill visual state
 *     (Req 1.5.3, 1.5.4).
 *   - Clicking a chip selects it (dusk fill) and clears the previous
 *     selection (Req 1.5.4).
 *   - Controlled mode honors the `selected` prop and does not mutate
 *     internal state on click — the parent owns the value.
 *   - `onChange` fires with the clicked label.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import CategoryChips from './CategoryChips'
import { CATEGORY_CHIPS } from '../copy'

describe('CategoryChips — ordering and default selection (Req 1.5.3)', () => {
  it('renders all 7 chips in the storefront-documented order', () => {
    render(<CategoryChips />)

    const chips = screen.getAllByRole('button')
    expect(chips).toHaveLength(CATEGORY_CHIPS.length)
    expect(chips.map(c => c.textContent)).toEqual([
      'All',
      'Linen',
      'Dresses',
      'Accessories',
      'Outerwear',
      'Footwear',
      'Home',
    ])
  })

  it('selects "All" by default and marks it active', () => {
    render(<CategoryChips />)
    const all = screen.getByTestId('category-chip-all')
    expect(all).toHaveAttribute('data-active', 'true')
    expect(all).toHaveAttribute('aria-pressed', 'true')
  })

  it('all other chips are inactive by default', () => {
    render(<CategoryChips />)
    for (const label of CATEGORY_CHIPS.filter(l => l !== 'All')) {
      const chip = screen.getByTestId(`category-chip-${label.toLowerCase()}`)
      expect(chip).toHaveAttribute('data-active', 'false')
      expect(chip).toHaveAttribute('aria-pressed', 'false')
    }
  })
})

describe('CategoryChips — click behavior (Req 1.5.4)', () => {
  it('clicking a chip sets it active and fires onChange with the label', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<CategoryChips onChange={onChange} />)

    await user.click(screen.getByTestId('category-chip-linen'))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('Linen')
    expect(screen.getByTestId('category-chip-linen')).toHaveAttribute(
      'data-active',
      'true',
    )
    // Previous "All" selection is cleared.
    expect(screen.getByTestId('category-chip-all')).toHaveAttribute(
      'data-active',
      'false',
    )
  })

  it('clicking "All" reclaims the default selected state', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    render(<CategoryChips onChange={onChange} />)

    await user.click(screen.getByTestId('category-chip-dresses'))
    await user.click(screen.getByTestId('category-chip-all'))

    expect(onChange).toHaveBeenNthCalledWith(2, 'All')
    expect(screen.getByTestId('category-chip-all')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(screen.getByTestId('category-chip-dresses')).toHaveAttribute(
      'data-active',
      'false',
    )
  })

  it('only one chip is active at a time (single-select)', async () => {
    const user = userEvent.setup()
    render(<CategoryChips />)

    await user.click(screen.getByTestId('category-chip-footwear'))
    await user.click(screen.getByTestId('category-chip-home'))

    const actives = CATEGORY_CHIPS.filter(
      l =>
        screen
          .getByTestId(`category-chip-${l.toLowerCase()}`)
          .getAttribute('data-active') === 'true',
    )
    expect(actives).toEqual(['Home'])
  })
})

describe('CategoryChips — controlled mode', () => {
  it('honors `selected` prop and does not mutate internal state on click', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()

    const { rerender } = render(
      <CategoryChips selected="Accessories" onChange={onChange} />,
    )

    expect(screen.getByTestId('category-chip-accessories')).toHaveAttribute(
      'data-active',
      'true',
    )

    await user.click(screen.getByTestId('category-chip-outerwear'))
    // Parent controls the value: without a rerender, the active chip
    // stays pinned to Accessories.
    expect(onChange).toHaveBeenCalledWith('Outerwear')
    expect(screen.getByTestId('category-chip-accessories')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(screen.getByTestId('category-chip-outerwear')).toHaveAttribute(
      'data-active',
      'false',
    )

    // Rerender with the new value to confirm it picks up.
    rerender(<CategoryChips selected="Outerwear" onChange={onChange} />)
    expect(screen.getByTestId('category-chip-outerwear')).toHaveAttribute(
      'data-active',
      'true',
    )
  })

  it('treats null selected as All for robustness', () => {
    render(<CategoryChips selected={null} />)
    expect(screen.getByTestId('category-chip-all')).toHaveAttribute(
      'data-active',
      'true',
    )
  })
})
