import { describe, expect, it } from 'vitest'
import { nameKey, sharedNames } from './sharedNames'

describe('sharedNames', () => {
  it('finds names two cards in one grid share, ignoring case and spaces', () => {
    const grid = [{ name: 'Linen Overshirt' }, { name: 'Hadley Linen Shirt' }, { name: ' linen overshirt' }]
    expect([...sharedNames(grid)]).toEqual(['linen overshirt'])
    expect(sharedNames(grid).has(nameKey('Linen Overshirt'))).toBe(true)
  })

  it('finds nothing when every name is unique, so no card changes', () => {
    expect(sharedNames([{ name: 'Cup' }, { name: 'Wabi-Sabi Bowl' }]).size).toBe(0)
    expect(sharedNames([]).size).toBe(0)
  })
})
