/**
 * ProductMiniCard tests — view-only product card inside a Turn.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ProductMiniCard from './ProductMiniCard'

describe('ProductMiniCard', () => {
  it('renders the name, price, and attribute line', () => {
    render(
      <ProductMiniCard
        name="Italian Linen Camp Shirt"
        price="$128"
        attributes="earl gray · relaxed"
      />,
    )
    expect(screen.getByText('Italian Linen Camp Shirt')).toBeInTheDocument()
    expect(screen.getByText('$128')).toBeInTheDocument()
    expect(screen.getByText('earl gray · relaxed')).toBeInTheDocument()
  })

  it('omits price and attributes when not provided', () => {
    render(<ProductMiniCard name="Plain Henley" />)
    expect(screen.getByText('Plain Henley')).toBeInTheDocument()
    expect(screen.queryByText(/^\$/)).not.toBeInTheDocument()
  })
})
