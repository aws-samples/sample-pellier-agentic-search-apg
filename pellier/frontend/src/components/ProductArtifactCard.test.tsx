import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ProductArtifactCard from './ProductArtifactCard'
import type { ChatProduct } from '../services/chat'

const PRODUCT: ChatProduct = {
  id: 41,
  name: 'Coral Lacquer Catchall',
  price: 325.36,
  image: '',
  category: 'Home',
}

describe('ProductArtifactCard shopping details', () => {
  it('labels missing stock evidence as not verified instead of checked', () => {
    render(<ProductArtifactCard product={PRODUCT} />)

    const details = screen.getByLabelText('Shopping details')
    const tag = within(details).getByTestId('status-tag')
    expect(tag).toHaveTextContent('Not verified')
    expect(tag).toHaveAttribute('data-tone', 'pending')
    expect(within(details).queryByText('Checked')).not.toBeInTheDocument()
  })

  it('shows only product facts carried by the storefront contract', () => {
    render(<ProductArtifactCard product={PRODUCT} />)

    const details = screen.getByLabelText('Shopping details')
    expect(within(details).getByText('Category')).toBeInTheDocument()
    expect(within(details).getByText('Home')).toBeInTheDocument()
    expect(within(details).queryByText('Material')).not.toBeInTheDocument()
    expect(within(details).queryByText('Service')).not.toBeInTheDocument()
  })

  it('renders the units the turn read across the warehouses', () => {
    render(<ProductArtifactCard product={{ ...PRODUCT, quantity: 4, inStock: true }} />)

    const details = screen.getByLabelText('Shopping details')
    const tag = within(details).getByTestId('status-tag')
    expect(tag).toHaveTextContent('In stock')
    expect(tag).toHaveAttribute('data-tone', 'good')
  })

  it('says how few are left when only a handful remain', () => {
    render(<ProductArtifactCard product={{ ...PRODUCT, quantity: 2, inStock: true }} />)

    const tag = within(screen.getByLabelText('Shopping details')).getByTestId('status-tag')
    expect(tag).toHaveTextContent('Only 2 left')
    expect(tag).toHaveAttribute('data-tone', 'good')
  })

  it('treats a prior purchase as collection context, not an item for sale', () => {
    render(
      <ProductArtifactCard
        product={{ ...PRODUCT, ownership: 'owned' }}
        onAddToCart={() => undefined}
      />,
    )

    expect(screen.getByText('Already in your collection')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to bag' })).toBeNull()
  })
})


describe('ProductArtifactCard rating', () => {
  it('never shows a review count as the star rating', () => {
    // Reviews but no rating: the card used to print "★ 1284 (1284)".
    const { container } = render(<ProductArtifactCard product={{ ...PRODUCT, reviews: 1284 }} />)
    expect(container.querySelector('.pa-rating')).toBeNull()
    expect(screen.queryByText('1284')).not.toBeInTheDocument()
  })

  it('shows a real rating to one decimal with its review count', () => {
    const { container } = render(<ProductArtifactCard product={{ ...PRODUCT, rating: 4.8, reviews: 312 }} />)
    expect(container.querySelector('.pa-rating')).toHaveTextContent('★ 4.8(312)')
  })

  it('shows no stars for a zero or missing rating', () => {
    const { container } = render(<ProductArtifactCard product={{ ...PRODUCT, rating: 0, reviews: 0 }} />)
    expect(container.querySelector('.pa-rating')).toBeNull()
  })
})

describe('ProductArtifactCard stock tag', () => {
  it('is red for a sold-out piece and green for an in-stock one', () => {
    render(<ProductArtifactCard product={{ ...PRODUCT, quantity: 0, inStock: false }} />)
    const soldOut = within(screen.getByLabelText('Shopping details')).getByTestId('status-tag')
    expect(soldOut).toHaveTextContent('Sold out')
    expect(soldOut).toHaveAttribute('data-tone', 'blocked')
  })
})
