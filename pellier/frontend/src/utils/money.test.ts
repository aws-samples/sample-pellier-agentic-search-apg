import { describe, expect, it } from 'vitest'
import { formatPrice } from './money'

describe('formatPrice', () => {
  it('keeps whole prices without cents, as the guide shows them', () => {
    expect(formatPrice(58)).toBe('$58')
    expect(formatPrice(78.0)).toBe('$78')
    expect(formatPrice(0)).toBe('$0')
  })

  it('shows cents to two places', () => {
    expect(formatPrice(49.5)).toBe('$49.50')
    expect(formatPrice(325.36)).toBe('$325.36')
  })

  it('separates thousands up to the largest price the catalog column holds', () => {
    expect(formatPrice(1284)).toBe('$1,284')
    expect(formatPrice(1284.5)).toBe('$1,284.50')
    expect(formatPrice(99999999.99)).toBe('$99,999,999.99')
  })
})
