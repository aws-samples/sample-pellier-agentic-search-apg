import { describe, expect, it } from 'vitest'
import { ANSWER_CARDS_MAX, productsNamedInAnswer } from './answerCards'

const piece = (name: string) => ({ name })
const CANDIDATES = ['Canvas Tote', 'Linen Apron', 'Stoneware Mugs', 'Wool Throw', 'Brass Bell'].map(piece)

describe('productsNamedInAnswer', () => {
  it('shows every piece the answer names, up to four, in the order it names them', () => {
    const answer = 'Start with the Wool Throw, then the Linen Apron, the Brass Bell and the Canvas Tote.'
    expect(productsNamedInAnswer(CANDIDATES, answer).map(p => p.name))
      .toEqual(['Wool Throw', 'Linen Apron', 'Brass Bell', 'Canvas Tote'])
  })

  it('stops at four when the answer names five', () => {
    const answer = 'Brass Bell, Wool Throw, Stoneware Mugs, Linen Apron and Canvas Tote all fit.'
    const cards = productsNamedInAnswer(CANDIDATES, answer)
    expect(ANSWER_CARDS_MAX).toBe(4)
    expect(cards.map(p => p.name)).toEqual(['Brass Bell', 'Wool Throw', 'Stoneware Mugs', 'Linen Apron'])
  })

  it('leaves out a piece the answer never names', () => {
    expect(productsNamedInAnswer(CANDIDATES, 'The Linen Apron is the one.').map(p => p.name)).toEqual(['Linen Apron'])
    expect(productsNamedInAnswer(CANDIDATES, 'Nothing fits that yet.')).toEqual([])
  })
})
