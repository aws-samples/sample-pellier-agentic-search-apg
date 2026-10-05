import { describe, expect, it } from 'vitest'
import {
  WORKSHOP_JOURNEYS,
  WORKSHOP_REQUIRED_PROMPTS,
  WORKSHOP_TURN_STAGES,
  journeyForLab,
  nextJourneyPrompt,
} from './workshopJourneys'

const EXPECTED = {
  marco: [
    'What linen do you have for 10 days in Goa?',
    'What would go with the Hadley Linen Shirt?',
    'How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?',
  ],
  anna: [
    'A housewarming gift for a friend who loves slow mornings. In stock, under $100, and no candles.',
    'A gift with a watch, under $100, in stock, no candles.',
    'Which one should I choose? Compare the two options using their current prices and availability.',
  ],
  theo: [
    'Hand-thrown ceramics for a slower morning routine',
    'What goes well with the pour-over set, keeping to the same materials and morning routine?',
    'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
  ],
  jessica: [
    'I sent two things back last week, the sage robe and the reed diffuser. Has anything been credited?',
    'What does your return policy say about store credit for returned home items?',
    'Please ask a person to look at a store credit for the two items I returned.',
  ],
} as const

describe('four-lab workshop journey contract', () => {
  it('retains the authored replay conversations and each anchor surface', () => {
    expect(WORKSHOP_TURN_STAGES).toEqual([
      'Establish context',
      'Exercise boundary',
      'Prove outcome',
    ])
    for (const [anchor, prompts] of Object.entries(EXPECTED)) {
      const journey = WORKSHOP_JOURNEYS[anchor as keyof typeof WORKSHOP_JOURNEYS]
      expect(journey.prompts).toEqual(prompts)
      expect(journey.prompts).toHaveLength(3)
    }
    expect(WORKSHOP_JOURNEYS.marco.surface).toBe('storefront')
    expect(WORKSHOP_JOURNEYS.anna.surface).toBe('storefront')
    expect(WORKSHOP_JOURNEYS.theo.surface).toBe('storefront')
    // Jessica is a shopper too: her case reaches the desk through Ask Pellier.
    expect(WORKSHOP_JOURNEYS.jessica.surface).toBe('storefront')
  })

  // Follow-up chips follow the current guide, without adding optional depth.
  describe('nextJourneyPrompt', () => {
    it("keeps each shopper's required prompts to their lab prompts", () => {
      expect(WORKSHOP_REQUIRED_PROMPTS).toEqual({
        marco: [
          'Is the Velvet Opera Cape in stock?',
          'How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?',
        ],
        anna: [
          'A housewarming gift for a friend who loves slow mornings. In stock, under $100, and no candles.',
          'A gift with a watch, under $100, in stock, no candles.',
        ],
        theo: [
          'Hand-thrown ceramics for a slower morning routine',
          'My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?',
          "Jessica and I share an address. She sent two things back last week and hasn't heard anything. Can you check her ticket too?",
        ],
        jessica: ['Please ask a person to look at a store credit for the two items I returned.'],
      })
    })

    it('takes each shopper through their lab prompts, and Marco nowhere past stock', () => {
      const theo = WORKSHOP_REQUIRED_PROMPTS.theo
      expect(nextJourneyPrompt(theo[0])).toBe(theo[1])
      expect(nextJourneyPrompt(theo[1])).toBe(theo[2])
      // Lab 2A's Spot, then the stock question Lab 2B judges, asked last.
      expect(nextJourneyPrompt('Is the Velvet Opera Cape in stock?')).toBe(WORKSHOP_JOURNEYS.marco.prompts[2])
      expect(nextJourneyPrompt(WORKSHOP_JOURNEYS.marco.prompts[2])).toBeUndefined()
      expect(nextJourneyPrompt(WORKSHOP_JOURNEYS.marco.prompts[0])).toBeUndefined()
      expect(nextJourneyPrompt(WORKSHOP_JOURNEYS.anna.prompts[0])).toBe(WORKSHOP_JOURNEYS.anna.prompts[1])
    })

    it('ends each required chat sequence at the guide’s stopping point', () => {
      for (const prompts of Object.values(WORKSHOP_REQUIRED_PROMPTS)) {
        expect(nextJourneyPrompt(prompts.at(-1))).toBeUndefined()
      }
    })

    it('ignores whitespace and casing, since the chip text is echoed back', () => {
      expect(
        nextJourneyPrompt('  hand-thrown CERAMICS for a   slower morning routine  '),
      ).toBe(WORKSHOP_REQUIRED_PROMPTS.theo[1])
    })

    // A fuzzy match would let an ordinary shopper question that merely
    // resembles a turn hijack the thread into a script nobody chose.
    it('does not fire on a question that only resembles a turn', () => {
      expect(nextJourneyPrompt('What linen do you have for Goa?')).toBeUndefined()
      expect(nextJourneyPrompt('Do you have linen shirts?')).toBeUndefined()
      expect(nextJourneyPrompt('')).toBeUndefined()
      expect(nextJourneyPrompt(undefined)).toBeUndefined()
    })
  })

  it('maps every Observatory lab id to its named anchor', () => {
    expect(journeyForLab('grounded-inventory')).toBe(WORKSHOP_JOURNEYS.marco)
    expect(journeyForLab('retrieval-acceptance')).toBe(WORKSHOP_JOURNEYS.anna)
    expect(journeyForLab('managed-agent-path')).toBe(WORKSHOP_JOURNEYS.theo)
    expect(journeyForLab('fail-closed-policy')).toBe(WORKSHOP_JOURNEYS.jessica)
  })
})
