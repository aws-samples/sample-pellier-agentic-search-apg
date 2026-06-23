import { describe, expect, it } from 'vitest'
import { PERSONA_HERO_PILLS, PERSONA_TURN_TRACES } from '../../data/personaCurations'
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
    'What would go with the Hadley shirt?',
    "What's the price range for linen shirts?",
    'Is the Hadley shirt at the Brooklyn warehouse?',
    "Can you connect me with a real Pellier stylist? I want a person to help me pick what to wear to my brother's wedding – not product cards.",
  ],
  anna: [
    'A thoughtful gift for someone who loves morning rituals',
    'Something beautiful under $100',
    'Help me pair a candle with something else',
    'Wrap-ready gifts with no extra effort',
    'Can you connect me with a real stylist? My friend just lost her mother and I want a person to help me pick a sympathy gift, not just see product cards.',
  ],
  theo: [
    'Hand-thrown ceramics for a slower morning routine',
    'What goes well with the pour-over set?',
    'Linen pieces that soften over seasons',
    "My Wabi-Sabi Bowl arrived chipped. Please file a damaged return – my customer id is 'theo'.",
    'The linen throw I bought 4 months ago developed a tear at the seam – I know the standard window closed but pieces like this should last. Can you handle this as an exception?',
  ],
} satisfies Record<(typeof CANONICAL_PERSONAS)[number], string[]>

const EXPECTED_TRACES = {
  marco: [
    { skill: 'the-packing-list', tools: ['find_pieces'] },
    { skill: 'the-packing-list', tools: ['find_pieces', 'style_match'] },
    { tools: ['price_intelligence'] },
    { tools: ['floor_check'] },
    { skill: 'the-packing-list', tools: ['escalate_to_stylist'] },
  ],
  anna: [
    { skill: 'the-gift-table', tools: ['find_pieces_hybrid'] },
    { skill: 'the-gift-table', tools: ['find_pieces_hybrid'] },
    { skill: 'the-gift-table', tools: ['find_pieces_hybrid'] },
    { skill: 'the-gift-table', tools: ['find_pieces_hybrid'] },
    { skill: 'the-gift-table', tools: ['escalate_to_stylist'] },
  ],
  theo: [
    { skill: 'the-makers-shelf', tools: ['find_pieces'] },
    { skill: 'the-makers-shelf', tools: ['find_pieces', 'style_match'] },
    { skill: 'the-makers-shelf', tools: ['find_pieces'] },
    { skill: 'the-makers-shelf', tools: ['find_pieces', 'returns_and_care', 'process_return'] },
    { skill: 'the-makers-shelf', tools: ['escalate_to_stylist'] },
  ],
} satisfies Pick<typeof PERSONA_TURN_TRACES, (typeof CANONICAL_PERSONAS)[number]>

const FIXTURE_ENTRYPOINTS = [
  { session: marcoOpening, expected: PERSONA_HERO_PILLS.marco[0] },
  { session: marcoMidpoint, expected: PERSONA_HERO_PILLS.marco[3] },
  { session: marcoCapstone, expected: PERSONA_HERO_PILLS.marco[4] },
  { session: annaMorningRitual, expected: PERSONA_HERO_PILLS.anna[0] },
  { session: annaUnder100, expected: PERSONA_HERO_PILLS.anna[1] },
  { session: annaCandlePairing, expected: PERSONA_HERO_PILLS.anna[2] },
  { session: annaBirthdayGift, expected: PERSONA_HERO_PILLS.anna[3] },
  { session: annaHousewarming, expected: PERSONA_HERO_PILLS.anna[4] },
  { session: theoPourOver, expected: PERSONA_HERO_PILLS.theo[0] },
  { session: theoPourOverPairing, expected: PERSONA_HERO_PILLS.theo[1] },
  { session: theoLinenSeasons, expected: PERSONA_HERO_PILLS.theo[2] },
  { session: theoCeramicsReturn, expected: PERSONA_HERO_PILLS.theo[3] },
  { session: theoHomeNotWardrobe, expected: PERSONA_HERO_PILLS.theo[4] },
] as const

describe('persona turn alignment', () => {
  it('keeps Marco, Anna, and Theo at exactly five canonical Boutique turns', () => {
    for (const persona of CANONICAL_PERSONAS) {
      expect(PERSONA_HERO_PILLS[persona]).toHaveLength(5)
      expect(PERSONA_HERO_PILLS[persona]).toEqual(EXPECTED_TURNS[persona])
    }
  })

  it('keeps Atelier replay entrypoints aligned with Boutique turn strings', () => {
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
