import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CartProvider, useCart } from './CartContext'

let persona: { id: string } | null = { id: 'anna' }

vi.mock('./PersonaContext', () => ({ usePersona: () => ({ persona }) }))
vi.mock('./LayoutContext', () => ({ useLayout: () => ({ workshopMode: 'default' }) }))

const MUG = { productId: 7, name: 'Stoneware mug', price: 18, origin: 'manual' as const }

describe('CartProvider across shoppers', () => {
  beforeEach(() => {
    persona = { id: 'anna' }
    localStorage.clear()
    localStorage.setItem('pellier-session-id', 'session-1')
  })

  it('empties the bag when a different shopper is chosen', () => {
    const { result, rerender } = renderHook(() => useCart(), { wrapper: CartProvider })
    act(() => result.current.addToCart(MUG))
    expect(result.current.items).toHaveLength(1)

    persona = { id: 'marco' }
    rerender()

    expect(result.current.items).toHaveLength(0)
    expect(JSON.parse(localStorage.getItem('pellier-cart') ?? '[]')).toEqual([])
  })

  it('empties the bag when the shopper signs out, so a guest never carries it', () => {
    const { result, rerender } = renderHook(() => useCart(), { wrapper: CartProvider })
    act(() => result.current.addToCart(MUG))

    persona = null
    rerender()

    expect(result.current.items).toHaveLength(0)
  })

  it('keeps the bag when the same shopper is restored after a reload', () => {
    persona = null
    const { result, rerender } = renderHook(() => useCart(), { wrapper: CartProvider })
    act(() => result.current.addToCart(MUG))

    persona = { id: 'anna' }
    rerender()

    expect(result.current.items).toHaveLength(1)
  })
})
