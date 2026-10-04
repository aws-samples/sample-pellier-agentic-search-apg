/**
 * ProductGrid tests — render contract.
 *
 * The grid renders the supplied live catalog rows synchronously. The earlier parallax
 * reveal was dropped (see ProductCard.tsx header comment) because the
 * pre-reveal `opacity: 0` left the grid invisible in real browsers whenever
 * IntersectionObserver didn't fire — the landmark can't hide itself.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'

import ProductGrid from './ProductGrid'
import { SHOWCASE_PRODUCTS } from '../data/showcaseProducts'

// Cards link to /product/:id, so the grid needs router context.
function renderGrid(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('ProductGrid — render contract', () => {
  it('renders all 9 showcase cards in declaration order', () => {
    renderGrid(<ProductGrid products={SHOWCASE_PRODUCTS} />)

    for (const [index, product] of SHOWCASE_PRODUCTS.entries()) {
      const card = screen.getByTestId(`product-card-${product.id}`)
      expect(card).toBeInTheDocument()
      expect(card).toHaveAttribute('data-index', String(index % 3))
    }
  })

  it('renders brand, name, price and one plain stock line per card, and no bag button', () => {
    const [first] = SHOWCASE_PRODUCTS
    renderGrid(
      <ProductGrid
        products={[
          { ...first, quantity: 12, warehouses: [] },
          { ...SHOWCASE_PRODUCTS[1], quantity: 0, warehouses: [] },
          {
            ...SHOWCASE_PRODUCTS[2],
            quantity: 20,
            warehouses: [
              { warehouseId: 'BK-01', name: 'Brooklyn', city: 'Brooklyn, NY', quantity: 0 },
              { warehouseId: 'ATX-02', name: 'Austin', city: 'Austin, TX', quantity: 6 },
              { warehouseId: 'PDX-03', name: 'Portland', city: 'Portland, OR', quantity: 14 },
            ],
          },
        ]}
      />,
    )

    const card = screen.getByTestId(`product-card-${first.id}`)
    expect(within(card).getByText(first.brand)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: first.name })).toHaveAttribute('href', `/product/${first.id}`)
    expect(within(card).getByText(`$${first.price}`)).toBeInTheDocument()
    expect(within(card).getByTestId('status-tag')).toHaveTextContent('In stock')
    expect(within(card).getByTestId('status-tag')).toHaveAttribute('data-tone', 'good')
    expect(within(card).queryByRole('button')).not.toBeInTheDocument()

    const soldOut = screen.getByTestId(`product-card-${SHOWCASE_PRODUCTS[1].id}`)
    expect(within(soldOut).getByTestId('status-tag')).toHaveTextContent('Sold out')
    expect(within(soldOut).getByTestId('status-tag')).toHaveAttribute('data-tone', 'blocked')

    const partial = screen.getByTestId(`product-card-${SHOWCASE_PRODUCTS[2].id}`)
    expect(within(partial).getByTestId('status-tag')).toHaveTextContent('In stock in Austin and Portland')
  })

  it('respects the `products` prop when provided', () => {
    const subset = SHOWCASE_PRODUCTS.slice(0, 3)
    renderGrid(<ProductGrid products={subset} />)

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
