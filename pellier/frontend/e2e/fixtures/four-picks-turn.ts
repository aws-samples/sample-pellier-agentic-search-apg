/**
 * Anna's recorded turn with an answer that names four pieces: the three of
 * her recorded answer, then the Wabi-Sabi Bowl, the fourth piece of the same
 * reranked result. Every other event is the recorded turn's, so the search,
 * its result and its ranking are unchanged. Ask Pellier shows all four as
 * cards, two by two, and the page tags all four "Pellier's pick", in the
 * answer's order.
 */
import { ANNA_TURN_EVENTS } from './anna-turn'

type TurnEvent = Record<string, unknown> & { type: string }

const RECORDED = ANNA_TURN_EVENTS as TurnEvent[]

// The fourth card, in the shape `chat.py` emits; its catalog fields are the
// recorded card's (`anna-cards.ts`, id 37).
const WABI_SABI_BOWL = {
  id: '37', name: 'Wabi-Sabi Bowl', brand: 'Pellier', color: 'Cream', price: 24, rating: 4.9, reviews: 167,
  category: 'Kitchen and table', image: '/products/theo-wabi-sabi-bowl.webp', badge: null,
  tags: ['ceramic', 'slow', 'home', 'neutral'], ownership: null, quantity: 24, inStock: true,
  originalPrice: null, discountPercent: 0,
}

const PRODUCTS = [
  ...RECORDED.filter(event => event.type === 'product').map(event => event.product),
  WABI_SABI_BOWL,
]

const ANSWER =
  'For slow mornings, start with the Stoneware Pour-Over Set at $58, a stoneware dripper and carafe that brews two cups by hand. ' +
  'Add the Ceramic Tumblers at $34 for juice at breakfast, and the Linen Napkins, Set of 4 at $44, which arrive gift-boxed. ' +
  'The Wabi-Sabi Bowl at $24 holds fruit or a morning yogurt. ' +
  'All four are in stock and under $100.'

/** The answer's four cards, in the order it names them. */
export const FOUR_PICKS: readonly string[] = ['31', '36', '22', '37']

function deltas(text: string): TurnEvent[] {
  return text.split(/(?<=\s)/).map(piece => ({ type: 'content_delta', delta: piece }))
}

function withAnswer(events: TurnEvent[]): TurnEvent[] {
  const out: TurnEvent[] = []
  for (const event of events) {
    if (event.type === 'content_delta') {
      if (!out.some(prior => prior.type === 'content_delta')) out.push(...deltas(ANSWER))
      continue
    }
    if (event.type === 'product') {
      if (!out.some(prior => prior.type === 'product')) {
        out.push(...PRODUCTS.map((product, index) => ({ type: 'product', product, index, total: PRODUCTS.length })))
      }
      continue
    }
    if (event.type === 'complete') {
      const response = event.response as Record<string, unknown>
      out.push({ ...event, response: { ...response, response: ANSWER, products: PRODUCTS } })
      continue
    }
    out.push(event)
  }
  return out
}

export const FOUR_PICKS_EVENTS: object[] = withAnswer(RECORDED)
