import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import ProductCard from './ProductCard'
import type { PellierProduct } from '../services/types'

const PRODUCT: PellierProduct = {
  id: 905,
  brand: 'Pellier',
  name: 'Waffle Bath Robe',
  color: 'Sage',
  price: 64,
  rating: 4.4,
  reviewCount: 12,
  category: 'Bath and body',
  imageUrl: '/products/missing-photo-for-this-piece.webp',
  tags: ['bath'],
  quantity: 3,
}

function renderCard(product: PellierProduct = PRODUCT) {
  return render(<MemoryRouter><ProductCard product={product} index={0} /></MemoryRouter>)
}

describe('ProductCard', () => {
  it('leaves the frame empty when the photo fails, instead of a broken image and its alt text', () => {
    const { container } = renderCard()
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    fireEvent.error(img as HTMLImageElement)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('.pellier-card-photo')).not.toBeNull()
    expect(screen.getByTestId('product-card-link-905')).toHaveTextContent('Waffle Bath Robe')
  })

  it('formats the price through the shared formatter', () => {
    renderCard({ ...PRODUCT, price: 1284 })
    expect(screen.getByText('$1,284')).toBeInTheDocument()
  })

  it('shows the colour only when another card in the grid shares the name', () => {
    const { container, rerender } = renderCard({ ...PRODUCT, name: 'Linen Overshirt', color: 'Olive' })
    expect(container.querySelector('.pellier-card-color')).toBeNull()
    rerender(<MemoryRouter><ProductCard product={{ ...PRODUCT, name: 'Linen Overshirt', color: 'Olive' }} index={0} showColor /></MemoryRouter>)
    expect(container.querySelector('.pellier-card-color')).toHaveTextContent('Olive')
  })
})

