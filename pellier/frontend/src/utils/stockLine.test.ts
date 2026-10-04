import { describe, expect, it } from 'vitest'
import { stockLine } from './stockLine'

describe('stockLine', () => {
  it('is green "In stock" when every warehouse holds the piece', () => {
    expect(stockLine({
      quantity: 20,
      warehouses: [
        { city: 'Brooklyn, NY', quantity: 4 },
        { city: 'Austin, TX', quantity: 6 },
      ],
    })).toEqual({ tone: 'good', label: 'In stock' })
  })

  it('names the cities that hold it when some do not', () => {
    expect(stockLine({
      quantity: 20,
      warehouses: [
        { city: 'Brooklyn, NY', quantity: 0 },
        { city: 'Austin, TX', quantity: 6 },
        { city: 'Portland, OR', quantity: 14 },
      ],
    })).toEqual({ tone: 'good', label: 'In stock in Austin and Portland' })
    expect(stockLine({
      warehouses: [
        { city: 'Brooklyn, NY', quantity: 0 },
        { city: 'Austin, TX', quantity: 6 },
      ],
    })).toEqual({ tone: 'good', label: 'In stock in Austin' })
  })

  it('is red "Sold out" when no warehouse holds it', () => {
    expect(stockLine({
      quantity: 0,
      warehouses: [
        { city: 'Brooklyn, NY', quantity: 0 },
        { city: 'Austin, TX', quantity: 0 },
      ],
    })).toEqual({ tone: 'blocked', label: 'Sold out' })
  })

  it('falls back to the catalog quantity without warehouse rows', () => {
    expect(stockLine({ quantity: 3, warehouses: [] })).toEqual({ tone: 'good', label: 'In stock' })
    expect(stockLine({ quantity: 0 })).toEqual({ tone: 'blocked', label: 'Sold out' })
  })

  it('is grey when stock was not read, never zero', () => {
    expect(stockLine({})).toEqual({ tone: 'pending', label: 'Not verified' })
    expect(stockLine({ quantity: null, warehouses: null })).toEqual({ tone: 'pending', label: 'Not verified' })
  })
})
