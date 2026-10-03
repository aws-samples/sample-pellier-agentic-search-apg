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
    expect(within(details).getByText('Stock')).toBeInTheDocument()
    expect(within(details).getByText('Not verified')).toBeInTheDocument()
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

  it('renders reconciled inventory carried by the chat response', () => {
    render(
      <ProductArtifactCard
        product={{
          ...PRODUCT,
          quantity: 50,
          inStock: true,
          availability: {
            status: 'reconciled_in_stock',
            availableQuantity: 4,
          },
        }}
      />,
    )

    const details = screen.getByLabelText('Shopping details')
    expect(within(details).getByText('4 available')).toBeInTheDocument()
  })

  it('does not turn an unresolved catalog quantity into an availability claim', () => {
    render(
      <ProductArtifactCard
        product={{
          ...PRODUCT,
          quantity: 50,
          inStock: true,
          availability: { status: 'availability_not_verified' },
        }}
      />,
    )

    expect(within(screen.getByLabelText('Shopping details')).getByText('Not verified')).toBeInTheDocument()
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
