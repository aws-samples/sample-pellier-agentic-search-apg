export const WORKSHOP_TURN_STAGES = [
  'Establish context',
  'Exercise boundary',
  'Prove outcome',
] as const

export type WorkshopTurnStage = (typeof WORKSHOP_TURN_STAGES)[number]
export type WorkshopAnchorId = 'marco' | 'anna' | 'theo' | 'jessica'
export type WorkshopJourneySurface = 'storefront'
export type WorkshopLabId =
  | 'grounded-inventory'
  | 'retrieval-acceptance'
  | 'managed-agent-path'
  | 'fail-closed-policy'

export interface WorkshopJourney {
  anchorId: WorkshopAnchorId
  anchorName: 'Marco' | 'Anna' | 'Theo' | 'Jessica'
  customerId: 'CUST-MARCO' | 'CUST-ANNA' | 'CUST-THEO' | 'CUST-JESSICA'
  labId: WorkshopLabId
  surface: WorkshopJourneySurface
  /** Authored conversations retained for optional replay and historical recordings. */
  prompts: readonly [string, string, string]
}

export const WORKSHOP_JOURNEYS: Record<WorkshopAnchorId, WorkshopJourney> = {
  marco: {
    anchorId: 'marco',
    anchorName: 'Marco',
    customerId: 'CUST-MARCO',
    labId: 'grounded-inventory',
    surface: 'storefront',
    prompts: [
      'What linen do you have for 10 days in Goa?',
      'What would go with the Hadley Linen Shirt?',
      'How many Hadley Linen Shirts are available at the Brooklyn warehouse, and what ship window is recorded?',
    ],
  },
  anna: {
    anchorId: 'anna',
    anchorName: 'Anna',
    customerId: 'CUST-ANNA',
    labId: 'retrieval-acceptance',
    surface: 'storefront',
    prompts: [
      'A housewarming gift for a friend who loves slow mornings. In stock, under $100, and no candles.',
      'A gift with a watch, under $100, in stock, no candles.',
      'Wrap-ready gifts with no extra effort',
    ],
  },
  theo: {
    anchorId: 'theo',
    anchorName: 'Theo',
    customerId: 'CUST-THEO',
    labId: 'managed-agent-path',
    surface: 'storefront',
    prompts: [
      'Hand-thrown ceramics for a slower morning routine',
      'What goes well with the pour-over set, keeping to the same materials and morning routine?',
      'My Wabi-Sabi Bowl arrived chipped. Please help me return it.',
    ],
  },
  jessica: {
    anchorId: 'jessica',
    anchorName: 'Jessica',
    customerId: 'CUST-JESSICA',
    labId: 'fail-closed-policy',
    surface: 'storefront',
    prompts: [
      'I sent two things back last week, the sage robe and the reed diffuser. Has anything been credited?',
      'What does your return policy say about store credit for returned home items?',
      'Please ask a person to look at a store credit for the two items I returned.',
    ],
  },
}

/**
 * The guide's required chat requests: each shopper's lab prompts, in order.
 * Anna's states the three limits her starter fallback drops, then the
 * challenge; Marco asks about a piece Pellier does not carry (Lab 2A's Spot),
 * then his Brooklyn stock question, last, because Lab 2B judges his latest
 * Stock-agent turn. SQL benchmarks, direct Gateway probes, Memory reads, and
 * human review actions remain separate guide steps. The home page's signed-in
 * suggestion row reads the same roles from `data/scenarios.json`
 * (`/api/scenarios`), so the two agree.
 */
export const WORKSHOP_REQUIRED_PROMPTS: Record<WorkshopAnchorId, readonly string[]> = {
  marco: ['Is the Velvet Opera Cape in stock?', WORKSHOP_JOURNEYS.marco.prompts[2]],
  anna: [WORKSHOP_JOURNEYS.anna.prompts[0], WORKSHOP_JOURNEYS.anna.prompts[1]],
  theo: [
    WORKSHOP_JOURNEYS.theo.prompts[0],
    'My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?',
    "Jessica and I share an address. She sent two things back last week and hasn't heard anything. Can you check her ticket too?",
  ],
  jessica: [WORKSHOP_JOURNEYS.jessica.prompts[2]],
}

/**
 * The next scripted prompt after `query`, when `query` is a journey turn.
 *
 * The storefront pins this as the first follow-up chip so a shopper who
 * clicked Marco's turn 1 is offered turn 2 rather than a generic catalog
 * action. Two things make that safe to force: the room is on a clock and the
 * journey is the demo, and the chip is the participant's own next step rather
 * than a claim about the answer.
 *
 * Matching is exact after normalisation, deliberately. A fuzzy match would let
 * an ordinary shopper question that merely resembles a turn hijack the thread
 * into a script they never chose. The pills send these strings verbatim, so
 * exact is the behaviour that is wanted.
 *
 * Returns undefined for the last turn: a journey that has ended has no next
 * step, and inventing one would push past the bounded path.
 */
function normalizePrompt(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

export function nextJourneyPrompt(
  query: string | null | undefined,
): string | undefined {
  if (!query) return undefined
  const needle = normalizePrompt(query)
  if (!needle) return undefined
  for (const prompts of Object.values(WORKSHOP_REQUIRED_PROMPTS)) {
    const turn = prompts.findIndex(
      (prompt) => normalizePrompt(prompt) === needle,
    )
    if (turn >= 0 && turn + 1 < prompts.length) {
      return prompts[turn + 1]
    }
  }
  return undefined
}

const JOURNEY_BY_LAB = new Map(
  Object.values(WORKSHOP_JOURNEYS).map((journey) => [journey.labId, journey]),
)

export function journeyForLab(
  labId: string | null | undefined,
): WorkshopJourney | undefined {
  return labId ? JOURNEY_BY_LAB.get(labId as WorkshopLabId) : undefined
}

/** Predictions and evidence checks are learning guidance, never claims about a run. */
export const WORKSHOP_EVIDENCE_GUIDANCE = {
  "marco": {
    "prediction": "A named item and warehouse should produce a scoped inventory read with quantity and a recorded ship window.",
    "evidence": "Inspect the resolved product, Brooklyn warehouse, quantity, ship window, tool arguments, and execution receipt. A dispatch window does not prove a delivery date.",
    "challenge": "Compare an unknown product with the sold-out Quilted Silk Vest.",
    "inspect": "Explain why not_found carries no inventory count, while a known product with zero stock still has warehouse rows. A missing record is not a verified zero."
  },
  "anna": {
    "prediction": "Price and stock constraints should determine eligibility before relevance ranking.",
    "evidence": "Inspect the PostgreSQL eligibility predicate, lexical and vector ranks, RRF contribution, rerank order, candidate coverage, quality metrics, and latency for the same measured query.",
    "challenge": "Keep the same recipient in mind, but make the budget under $70.",
    "inspect": "Verify that the new ceiling replaces the previous one while recipient context persists. Inspect the exact boundary predicate; the workshop benchmark uses an inclusive price ceiling."
  },
  "theo": {
    "prediction": "The managed agent should preserve the conversation and keep customer-scoped tool calls bound to the verified caller, including a request that names another customer.",
    "evidence": "Check verified caller, Runtime build fingerprint, Gateway tool arguments and results, independent Memory records, and the separate direct Gateway denial. A model refusal alone does not prove the Gateway boundary.",
    "challenge": "I prefer matte glazes and compact pieces for my breakfast tray.",
    "inspect": "Verify the new preference in a Memory event using the guide’s independent process. Then ask “Which pairing suits my routine?” without repeating it. This tests conversation continuity. Use the separate new-session Memory check and extracted record IDs to prove learned preferences."
  },
  "jessica": {
    "prediction": "Reported context should remain distinct from authoritative records, and human confirmation should remain separate from authorization and execution.",
    "evidence": "Inspect the principal/customer pairing, policy decision, correlated tool execution or absence, durable effect, replay behavior, rollback-only RLS result, and the confirmed review linked to its execution and return row.",
    "challenge": "Have we handled something similar before? Show the outcome and explain what must be checked again.",
    "inspect": "Use prior-resolution recall as context. Previous receipts grant no current authority; an empty result is valid. Resolve conflicting support notes against the authoritative ledger."
  }
} as const
