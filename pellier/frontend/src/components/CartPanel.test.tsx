import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const handleCheckout = vi.fn()
const confirmAndPlaceOrder = vi.fn()
const resetCheckout = vi.fn()
const login = vi.fn()
let isAuthenticated: boolean

const quote = {
  quoteId: 'quote-1',
  quoteHash: 'a'.repeat(64),
  status: 'open',
  currency: 'USD',
  lines: [],
  amounts: {
    subtotal: '80.00',
    shipping: '12.00',
    tax: '6.60',
    total: '98.60',
  },
  rules: {
    policy: 'pellier-commerce-v1',
    taxRate: '0.0825',
    freeShippingThreshold: '150.00',
    standardShipping: '12.00',
    paymentProvider: 'pellier-sandbox',
    paymentMode: 'sandbox',
  },
  expiresAt: '2026-08-16T20:10:00+00:00',
}

let cartState: Record<string, unknown>

vi.mock('../contexts/CartContext', () => ({
  useCart: () => cartState,
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated, login }),
}))

import CartPanel from './CartPanel'

beforeEach(() => {
  handleCheckout.mockReset()
  confirmAndPlaceOrder.mockReset()
  resetCheckout.mockReset()
  login.mockReset()
  isAuthenticated = true
  cartState = {
    items: [{
      productId: 7,
      name: 'Linen Field Jacket',
      price: 80,
      quantity: 1,
      origin: 'manual',
      addedAt: 1,
    }],
    updateQuantity: vi.fn(),
    removeFromCart: vi.fn(),
    handleCheckout,
    confirmAndPlaceOrder,
    checkoutStage: 'bag',
    checkoutQuote: null,
    checkoutReceipt: null,
    checkoutError: null,
    checkoutComplete: false,
    resetCheckout,
    clearCart: vi.fn(),
  }
})

describe('CartPanel proof-carrying checkout', () => {
  it('opens an accessible dialog outside the page, traps focus, and closes with Escape', () => {
    const onClose = vi.fn()
    const { container, unmount } = render(<CartPanel isOpen onClose={onClose} />)
    const dialog = screen.getByRole('dialog', { name: 'Your bag' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(container).not.toContainElement(dialog)
    expect(dialog).toHaveFocus()
    expect(document.body.style.overflow).toBe('hidden')
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: /review order/i })).toHaveFocus()
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

  it('does not claim a final total before the server quote', () => {
    render(<CartPanel isOpen onClose={vi.fn()} />)

    expect(screen.getByText('Calculated in review')).toBeInTheDocument()
    expect(screen.queryByText('Free')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /review order/i }))
    expect(handleCheckout).toHaveBeenCalledOnce()
  })

  it('requires explicit acknowledgement of the authoritative total', () => {
    cartState.checkoutStage = 'review'
    cartState.checkoutQuote = quote
    render(<CartPanel isOpen onClose={vi.fn()} />)

    expect(screen.getByText('$98.60')).toBeInTheDocument()
    const placeOrder = screen.getByRole('button', { name: /confirm and place order/i })
    expect(placeOrder).toBeDisabled()

    fireEvent.click(screen.getByRole('checkbox'))
    expect(placeOrder).toBeEnabled()
    fireEvent.click(placeOrder)
    expect(confirmAndPlaceOrder).toHaveBeenCalledOnce()
  })

  it('shows persisted evidence and the sandbox payment mode', () => {
    cartState.checkoutStage = 'complete'
    cartState.checkoutComplete = true
    cartState.checkoutReceipt = {
      orderId: 'order-1',
      orderNumber: 'PEL-ABC12345',
      status: 'paid',
      paymentStatus: 'settled',
      currency: 'USD',
      amounts: quote.amounts,
      payment: {
        provider: 'pellier-sandbox',
        mode: 'sandbox',
        status: 'settled',
      },
      evidence: {
        inventory: { status: 'captured' },
      },
      receipt: {
        receiptId: 'receipt-1',
        receiptHash: 'b'.repeat(64),
        verified: true,
        createdAt: '2026-08-16T20:00:00+00:00',
      },
    }
    render(<CartPanel isOpen onClose={vi.fn()} />)

    expect(screen.getByText('Order placed.')).toBeInTheDocument()
    expect(screen.getByText('Evidence receipt')).toBeInTheDocument()
    expect(screen.getByText('Verified')).toBeInTheDocument()
    expect(screen.getByText('Sandbox settled')).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`Receipt ${'b'.repeat(64)}`))).toBeInTheDocument()
  })

  it('keeps sign-in failure distinct and offers the sign-in action', () => {
    isAuthenticated = false
    cartState.checkoutStage = 'error'
    cartState.checkoutError = {
      code: 'sign_in_required',
      message: 'Sign in to review and place this order.',
    }
    render(<CartPanel isOpen onClose={vi.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Sign in to review')
    fireEvent.click(screen.getByRole('button', { name: /sign in to continue/i }))
    expect(login).toHaveBeenCalledOnce()
  })

  it('retries checkout after authentication instead of reopening sign-in', () => {
    cartState.checkoutStage = 'error'
    cartState.checkoutError = {
      code: 'sign_in_required',
      message: 'Sign in to review and place this order.',
    }
    render(<CartPanel isOpen onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /review order/i }))
    expect(handleCheckout).toHaveBeenCalledOnce()
    expect(login).not.toHaveBeenCalled()
  })
})
