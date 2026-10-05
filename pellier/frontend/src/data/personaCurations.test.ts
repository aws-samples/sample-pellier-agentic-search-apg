import { describe, expect, it } from 'vitest'
import { welcomeScene } from './welcomeScenes'

describe("each shopper's welcome", () => {
  it("gives Jessica her own scene rather than the guest's", () => {
    expect(welcomeScene('jessica')).not.toEqual(welcomeScene('fresh'))
  })
})
