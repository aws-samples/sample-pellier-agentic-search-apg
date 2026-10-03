import { describe, expect, it } from 'vitest'
import {
  catalogTurnFollowUps,
  productQuickActions,
} from './catalogFollowUps'

describe('catalog follow-ups', () => {
  it('never invents a colorway for a named catalog product', () => {
    const actions = productQuickActions({
      name: 'Italian Linen Camp Shirt',
      category: 'Clothing',
      price: 228,
    })

    expect(actions.map(action => action.label)).toEqual([
      'Build around it',
      'Similar pieces',
    ])
    expect(actions.map(action => action.prompt).join(' ')).not.toMatch(
      /another (?:size|color)|colorway/i,
    )
    expect(actions.map(action => action.prompt).join(' ')).not.toMatch(
      /stock|availability/i,
    )
  })

  it('builds turn follow-ups from products actually returned', () => {
    const prompts = catalogTurnFollowUps(
      [
        { name: 'Hadley Linen Shirt', price: 248 },
        { name: 'Oat Linen Drawstring Trousers', price: 178 },
      ],
      ['Static fallback'],
    )

    expect(prompts[0]).toBe(
      'Compare Hadley Linen Shirt and Oat Linen Drawstring Trousers.',
    )
    expect(prompts.join(' ')).not.toContain('Static fallback')
    expect(prompts.join(' ')).not.toMatch(/stock|availability/i)
  })
})
