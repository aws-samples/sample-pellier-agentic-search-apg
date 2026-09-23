export const WORKSHOP_TURN_STAGES = [
  'Establish context',
  'Exercise boundary',
  'Prove outcome',
] as const

export type WorkshopTurnStage = (typeof WORKSHOP_TURN_STAGES)[number]
export type WorkshopAnchorId = 'marco' | 'anna' | 'theo' | 'jessica'
export type WorkshopJourneySurface = 'storefront' | 'operator'
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
      'A housewarming gift for someone who loves slow morning rituals.',
      'Keep it under $100 and in stock. Show me the strongest two options.',
      'Which one should I choose? Compare the two options using their current prices and availability.',
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
    surface: 'operator',
    prompts: [
      "Investigate Jessica's open service issue (TKT-2026-3015) and recommend the next fair step. Distinguish what the records establish from what a source reports.",
      'Which customer, order, return, and identity records are authoritative for this decision? Separate confirmed facts from notes and assumptions.',
      'Prepare the fairest next step for human review without executing it. Name any missing facts the reviewer must resolve.',
    ],
  },
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
  for (const journey of Object.values(WORKSHOP_JOURNEYS)) {
    const turn = journey.prompts.findIndex(
      (prompt) => normalizePrompt(prompt) === needle,
    )
    if (turn >= 0 && turn + 1 < journey.prompts.length) {
      return journey.prompts[turn + 1]
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
    "prediction": "The managed agent should preserve the conversation and use its published, customer-scoped Gateway tools. Its return call can execute after authorization and business validation.",
    "evidence": "Check verified caller, Runtime build fingerprint, Gateway tool results, independent Memory records, and keyed Aurora effects. This managed call does not create the in-process path's human review.",
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
