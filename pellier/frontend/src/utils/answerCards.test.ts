import { describe, expect, it } from 'vitest'
import { ANSWER_CARDS_MAX, mentionOf, productsNamedInAnswer } from './answerCards'

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

  it('finds a piece whose catalog name carries an em-dash variant the answer leaves off', () => {
    const tray = { name: 'Hand-Thrown Stoneware Pour-Over Coffee Set with Two Speckled Tumblers and a Walnut Serving Tray — Ash Gray' }
    const answer = 'For a slow morning, the Hand-Thrown Stoneware Pour-Over Coffee Set with Two Speckled Tumblers and a Walnut Serving Tray is the pick.'
    expect(productsNamedInAnswer([tray], answer)).toEqual([tray])
  })

  it('matches whole words, so a short name never matches inside another word', () => {
    const cup = { name: 'Cup' }
    expect(productsNamedInAnswer([cup], 'It fits in a small cupboard.')).toEqual([])
    expect(productsNamedInAnswer([cup], 'The Cup is stoneware.')).toEqual([cup])
  })

  it('still matches a piece the answer names in the plural', () => {
    const shirt = { name: 'Hadley Linen Shirt' }
    expect(productsNamedInAnswer([shirt], 'Brooklyn has no Hadley Linen Shirts left.')).toEqual([shirt])
    expect(mentionOf('see the hadley linen shirt.', 'Hadley Linen Shirt')).toBe(8)
  })
})
