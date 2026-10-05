import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

let cartState: Record<string, unknown>

vi.mock('../contexts/CartContext', () => ({
  useCart: () => cartState,
}))

import CartPanel from './CartPanel'

beforeEach(() => {
  cartState = {
    items: [{
      productId: 7,
      name: 'Linen Field Jacket',
      price: 80,
      quantity: 2,
      origin: 'manual',
      addedAt: 1,
    }],
    updateQuantity: vi.fn(),
    removeFromCart: vi.fn(),
    clearCart: vi.fn(),
  }
})

describe('CartPanel, a bag that keeps a list', () => {
  it('opens an accessible dialog outside the page, traps focus, and closes with Escape', () => {
    const onClose = vi.fn()
    const { container, unmount } = render(<CartPanel isOpen onClose={onClose} />)
    const dialog = screen.getByRole('dialog', { name: 'Your bag' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(container).not.toContainElement(dialog)
    expect(dialog).toHaveFocus()
    expect(document.body.style.overflow).toBe('hidden')
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: 'Remove' })).toHaveFocus()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
    unmount()
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('gives an empty bag a direct way back to browsing', () => {
    cartState.items = []
    const onClose = vi.fn()
    render(<CartPanel isOpen onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Continue browsing' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('shows the subtotal and says plainly that no order is placed', () => {
    render(<CartPanel isOpen onClose={vi.fn()} />)

    expect(screen.getByText('Subtotal (2 items)')).toBeInTheDocument()
    expect(screen.getByText('$160.00', { selector: 'span.font-medium' })).toBeInTheDocument()
    expect(screen.getByText(/keeps a list and places no order/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /order|checkout/i })).not.toBeInTheDocument()
  })

  it('changes quantity and removes a piece through the bag', () => {
    render(<CartPanel isOpen onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Increase quantity' }))
    expect(cartState.updateQuantity).toHaveBeenCalledWith(7, 3)
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(cartState.removeFromCart).toHaveBeenCalledWith(7)
  })
})
