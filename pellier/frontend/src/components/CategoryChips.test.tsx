/**
 * CategoryChips tests — horizontal category filter row.
 *
 * Validates Requirements 1.5.3 and 1.5.4.
 *
 * Coverage:
 *   - Renders All plus the eight store departments from copy.ts in order
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

import CategoryChips, { categoryChipTestId } from './CategoryChips'
import { CATEGORY_CHIPS } from '../copy'

describe('CategoryChips — ordering and default selection (Req 1.5.3)', () => {
  it('renders All and the eight store departments in order', () => {
    render(<CategoryChips />)

    const chips = screen.getAllByRole('button')
    expect(chips).toHaveLength(CATEGORY_CHIPS.length)
    expect(chips.map(c => c.textContent)).toEqual([
      'All',
      'Clothing',
      'Shoes',
      'Bags and travel',
      'Accessories',
      'Home',
      'Kitchen and table',
      'Bath and body',
      'Stationery and gifts',
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
      const chip = screen.getByTestId(categoryChipTestId(label))
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

    await user.click(screen.getByTestId('category-chip-bags-and-travel'))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('Bags and travel')
    expect(screen.getByTestId('category-chip-bags-and-travel')).toHaveAttribute(
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

    await user.click(screen.getByTestId('category-chip-clothing'))
    await user.click(screen.getByTestId('category-chip-all'))

    expect(onChange).toHaveBeenNthCalledWith(2, 'All')
    expect(screen.getByTestId('category-chip-all')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(screen.getByTestId('category-chip-clothing')).toHaveAttribute(
      'data-active',
      'false',
    )
  })

  it('only one chip is active at a time (single-select)', async () => {
    const user = userEvent.setup()
    render(<CategoryChips />)

    await user.click(screen.getByTestId('category-chip-shoes'))
    await user.click(screen.getByTestId('category-chip-home'))

    const actives = CATEGORY_CHIPS.filter(
      l =>
        screen
          .getByTestId(categoryChipTestId(l))
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

    await user.click(screen.getByTestId('category-chip-kitchen-and-table'))
    // Parent controls the value: without a rerender, the active chip
    // stays pinned to Accessories.
    expect(onChange).toHaveBeenCalledWith('Kitchen and table')
    expect(screen.getByTestId('category-chip-accessories')).toHaveAttribute(
      'data-active',
      'true',
    )
    expect(screen.getByTestId('category-chip-kitchen-and-table')).toHaveAttribute(
      'data-active',
      'false',
    )

    // Rerender with the new value to confirm it picks up.
    rerender(<CategoryChips selected="Kitchen and table" onChange={onChange} />)
    expect(screen.getByTestId('category-chip-kitchen-and-table')).toHaveAttribute(
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
