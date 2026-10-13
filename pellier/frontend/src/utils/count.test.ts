import { describe, expect, it } from 'vitest'
import { HOME_GRID, RESULTS } from '../copy'
import { formatCount } from './count'

describe('formatCount', () => {
  it('leaves counts under a thousand as they read in the guide', () => {
    expect(formatCount(0)).toBe('0')
    expect(formatCount(64)).toBe('64')
    expect(formatCount(100)).toBe('100')
  })

  it('separates thousands', () => {
    expect(formatCount(1000)).toBe('1,000')
    expect(formatCount(1284)).toBe('1,284')
    expect(formatCount(50000)).toBe('50,000')
  })

  it('formats the results and catalog counts', () => {
    expect(RESULTS.shown(1)).toBe('1 piece')
    expect(RESULTS.shown(1284)).toBe('1,284 pieces')
    expect(HOME_GRID.range(13, 24, 50000)).toBe('13–24 of 50,000')
  })
})
