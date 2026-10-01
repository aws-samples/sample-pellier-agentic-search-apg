import { describe, expect, it } from 'vitest'
import { PERSONA_HERO_PILLS, PERSONA_TURN_TRACES } from '../../data/personaCurations'
import { WORKSHOP_JOURNEYS } from '../../data/workshopJourneys'
import sessions from '../fixtures/sessions.json'
import annaMorningRitual from '../fixtures/session-anna-morning-ritual.json'
import annaUnder100 from '../fixtures/session-anna-under-100.json'
import annaCandlePairing from '../fixtures/session-anna-candle-pairing.json'
import annaBirthdayGift from '../fixtures/session-anna-birthday-gift.json'
import annaHousewarming from '../fixtures/session-anna-housewarming.json'
import marcoCapstone from '../fixtures/session-marco-capstone.json'
import marcoMidpoint from '../fixtures/session-marco-midpoint-checkpoint.json'
import marcoOpening from '../fixtures/session-marco-opening-demo.json'
import theoCeramicsReturn from '../fixtures/session-theo-ceramics-return.json'
import theoHomeNotWardrobe from '../fixtures/session-theo-home-not-wardrobe.json'
import theoLinenSeasons from '../fixtures/session-theo-linen-seasons.json'
import theoPourOver from '../fixtures/session-theo-pour-over.json'
import theoPourOverPairing from '../fixtures/session-theo-pour-over-pairing.json'

const CANONICAL_PERSONAS = ['marco', 'anna', 'theo'] as const

const EXPECTED_TURNS = {
  marco: [
    'What linen do you have for 10 days in Goa?',
    'What would go with the Hadley Linen Shirt?',
    'How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?',
    "What's the price range for linen shirts?",
    "Can you connect me with a real Pellier stylist? I want a person to help me pick what to wear to my brother's wedding – not product cards.",
  ],
  anna: [
    'A housewarming gift for someone who loves slow morning rituals.',
    'Keep it under $100 and in stock. Show me the strongest two options.',
    'Which one should I choose? Compare the two options using their current prices and availability.',
    'Wrap-ready gifts with no extra effort',
    'Can you connect me with a real stylist? My friend just lost her mother and I want a person to help me pick a sympathy gift, not just see product cards.',
  ],
  theo: [
    'Hand-thrown ceramics for a slower morning routine',
    'What goes well with the pour-over set, keeping to the same materials and morning routine?',
    'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
    'Without asking me to repeat the ritual or material, which pairing should I choose and why?',
    'The linen throw I bought 4 months ago developed a tear at the seam – I know the standard window closed but pieces like this should last. Can you handle this as an exception?',
  ],
} satisfies Record<(typeof CANONICAL_PERSONAS)[number], string[]>

const EXPECTED_TRACES = {
  marco: [
    { skill: 'the-packing-list', tools: ['search_products'] },
    { skill: 'the-packing-list', tools: ['search_products', 'get_related_products'] },
    { tools: ['check_inventory'] },
    { tools: ['get_price_analysis'] },
    { skill: 'the-packing-list', tools: ['escalate_to_human'] },
  ],
  anna: [
    { skill: 'the-gift-table', tools: ['search_products_hybrid'] },
    { skill: 'the-gift-table', tools: ['search_products_hybrid'] },
    { skill: 'the-gift-table', tools: ['search_products_hybrid'] },
    { skill: 'the-gift-table', tools: ['search_products_hybrid'] },
    { skill: 'the-gift-table', tools: ['escalate_to_human'] },
  ],
  theo: [
    { skill: 'the-makers-shelf', tools: ['search_products'] },
    { skill: 'the-makers-shelf', tools: ['search_products', 'get_related_products'] },
    { skill: 'the-makers-shelf', tools: ['search_products', 'get_return_policy', 'initiate_return'] },
    { skill: 'the-makers-shelf', tools: [] },
    { skill: 'the-makers-shelf', tools: ['escalate_to_human'] },
  ],
} satisfies Pick<typeof PERSONA_TURN_TRACES, (typeof CANONICAL_PERSONAS)[number]>

const FIXTURE_ENTRYPOINTS = [
  { session: marcoOpening, expected: PERSONA_HERO_PILLS.marco[0] },
  { session: marcoMidpoint, expected: PERSONA_HERO_PILLS.marco[2] },
  { session: marcoCapstone, expected: PERSONA_HERO_PILLS.marco[4] },
  { session: annaMorningRitual, expected: PERSONA_HERO_PILLS.anna[0] },
  { session: annaUnder100, expected: PERSONA_HERO_PILLS.anna[1] },
  { session: annaCandlePairing, expected: PERSONA_HERO_PILLS.anna[2] },
  { session: annaBirthdayGift, expected: PERSONA_HERO_PILLS.anna[3] },
  { session: annaHousewarming, expected: PERSONA_HERO_PILLS.anna[4] },
  { session: theoPourOver, expected: PERSONA_HERO_PILLS.theo[0] },
  { session: theoPourOverPairing, expected: PERSONA_HERO_PILLS.theo[1] },
  { session: theoCeramicsReturn, expected: PERSONA_HERO_PILLS.theo[2] },
  { session: theoLinenSeasons, expected: PERSONA_HERO_PILLS.theo[3] },
  { session: theoHomeNotWardrobe, expected: PERSONA_HERO_PILLS.theo[4] },
] as const

describe('persona turn alignment', () => {
  it('keeps the historical authored conversations stable for their recordings', () => {
    for (const persona of CANONICAL_PERSONAS) {
      expect(PERSONA_HERO_PILLS[persona]).toHaveLength(5)
      expect(PERSONA_HERO_PILLS[persona]).toEqual(EXPECTED_TURNS[persona])
      expect(PERSONA_HERO_PILLS[persona].slice(0, 3)).toEqual(
        WORKSHOP_JOURNEYS[persona].prompts,
      )
    }
  })

  it('keeps Observatory replay entrypoints aligned with Pellier turn strings', () => {
    for (const { session, expected } of FIXTURE_ENTRYPOINTS) {
      expect(session.openingQuery).toBe(expected)
      expect(session.chat[0]?.role).toBe('user')
      expect(session.chat[0]?.content).toBe(expected)

      const listedSession = sessions.find((item) => item.id === session.id)
      expect(listedSession?.openingQuery).toBe(expected)
    }
  })

  it('keeps expected skills and tools aligned turn-by-turn', () => {
    for (const persona of CANONICAL_PERSONAS) {
      expect(PERSONA_TURN_TRACES[persona]).toHaveLength(5)
      expect(PERSONA_TURN_TRACES[persona]).toEqual(EXPECTED_TRACES[persona])
    }
  })
})
