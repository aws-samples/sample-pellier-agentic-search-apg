/**
 * ProductGrid tests — render contract.
 *
 * The grid renders every showcase product synchronously. The earlier parallax
 * reveal was dropped (see ProductCard.tsx header comment) because the
 * pre-reveal `opacity: 0` left the grid invisible in real browsers whenever
 * IntersectionObserver didn't fire — the landmark can't hide itself.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ProductGrid from './ProductGrid'
import { SHOWCASE_PRODUCTS } from '../data/showcaseProducts'

describe('ProductGrid — render contract', () => {
  it('renders all 9 showcase cards in declaration order', () => {
    render(<ProductGrid />)

    for (const [index, product] of SHOWCASE_PRODUCTS.entries()) {
      const card = screen.getByTestId(`product-card-${product.id}`)
      expect(card).toBeInTheDocument()
      expect(card).toHaveAttribute('data-index', String(index % 3))
    }
  })

  it('each card includes the warm wash overlay + Add to bag button', () => {
    render(<ProductGrid />)

    for (const product of SHOWCASE_PRODUCTS) {
      expect(
        screen.getByTestId(`product-card-add-${product.id}`),
      ).toBeInTheDocument()
    }
    expect(screen.getAllByTestId('product-card-warm-wash')).toHaveLength(
      SHOWCASE_PRODUCTS.length,
    )
  })

  it('respects the `products` prop when provided', () => {
    const subset = SHOWCASE_PRODUCTS.slice(0, 3)
    render(<ProductGrid products={subset} />)

    for (const product of subset) {
      expect(
        screen.getByTestId(`product-card-${product.id}`),
      ).toBeInTheDocument()
    }
    expect(
      screen.queryByTestId(`product-card-${SHOWCASE_PRODUCTS[4].id}`),
    ).toBeNull()
  })
})
