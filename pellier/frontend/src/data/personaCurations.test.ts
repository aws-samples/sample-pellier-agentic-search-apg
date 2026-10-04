import { describe, expect, it } from 'vitest'
import { storefrontEditFor } from './personaCurations'
import { welcomeScene } from './welcomeScenes'

describe("each shopper's storefront edit", () => {
  it('reads the neutral edit signed out, and each shopper their own grouping', () => {
    expect(storefrontEditFor(null)).toBe('fresh')
    expect(storefrontEditFor('marco')).toBe('marco')
    expect(storefrontEditFor('anna')).toBe('anna')
    expect(storefrontEditFor('theo')).toBe('theo')
  })

  it("gives Jessica the ranked Home comforts edit rather than the guest's", () => {
    expect(storefrontEditFor('jessica')).toBe('house')
    expect(welcomeScene('jessica')).not.toEqual(welcomeScene('fresh'))
  })
})
