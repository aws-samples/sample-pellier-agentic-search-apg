/**
 * personaCurations — the single source of truth for how each persona
 * reshapes the storefront's "Curated for you" ordering and
 * "Because you asked..." editorial lineup.
 *
 * Design:
 *   - Each persona declares a set of weighted tag interests. Those
 *     interests are applied against SHOWCASE_PRODUCTS[*].tags to
 *     compute a score per product; the Curated grid sorts products
 *     descending by score.
 *   - Each persona also declares its own ordered list of editorial
 *     cards for the "Because you asked..." band. Marco sees
 *     travel/linen cards first, Anna sees gift-focused, Theo sees
 *     home rituals.
 *   - The "fresh" persona (anonymous / first-time visitor) falls
 *     through to the canonical unbiased ordering — same product list,
 *     no scoring, and the generic editorial cards.
 *
 * Why not backend: the point of this round is the demo surface — the
 * personalization should be visible the instant an attendee picks a
 * persona from the welcome chip, no network round-trip. When a real
 * recommendation service ships, this file becomes a client-side
 * fallback that mirrors the server's ranking heuristic.
 */

import type { BoutiqueProduct } from '../services/types'

// ---------------------------------------------------------------------
// Persona interest profiles. Scores are 0-10; higher = stronger lean.
// Applied as a dot product against the product's tag set.
// ---------------------------------------------------------------------

export interface PersonaInterests {
  /** Tag → weight. Unmatched tags contribute 0. */
  tagWeights: Record<string, number>
  /** Optional section headline override. Falls back to canonical if unset. */
  curatedHeadline?: string
  /** Optional section eyebrow override. */
  curatedEyebrow?: string
}

export const PERSONA_INTERESTS: Record<string, PersonaInterests> = {
  marco: {
    // Natural fibers, travel-ready, timeless accessories. Marco reads
    // the storefront looking for pieces that hold up on the road and
    // get softer with wear.
    tagWeights: {
      linen: 10,
      travel: 9,
      leather: 8,
      classic: 7,
      warm: 6,
      earth: 6,
      timeless: 6,
      accessories: 5,
      minimal: 5,
      resort: 5,
      everyday: 4,
      neutral: 3,
    },
    curatedEyebrow: 'Curated for Marco',
    curatedHeadline: 'Pieces that travel.',
  },
  anna: {
    // Gift-focused, milestone occasions. Anna lands on the site with
    // a someone in mind — she wants pieces that arrive well-wrapped,
    // land across price bands, and read as considered.
    tagWeights: {
      candle: 10,
      beauty: 9,
      apothecary: 9,
      ceramic: 8,
      home: 7,
      sculptural: 7,
      artisanal: 7,
      warm: 6,
      minimal: 6,
      accessories: 5,
      timeless: 5,
      classic: 4,
    },
    curatedEyebrow: 'Curated for Anna',
    curatedHeadline: 'Gifts, thoughtfully matched.',
  },
  theo: {
    // Slow-craft, home rituals. Theo cares about ceramics, linen that
    // softens with washing, objects with patina. The home/wellness
    // cluster wins over travel or accessories.
    tagWeights: {
      ceramic: 10,
      slow: 10,
      artisanal: 9,
      home: 9,
      wellness: 8,
      linen: 8,
      sculptural: 7,
      minimal: 6,
      neutral: 5,
      warm: 5,
      loungewear: 5,
      candle: 4,
    },
    curatedEyebrow: 'Curated for Theo',
    curatedHeadline: 'Quiet pieces, lived-in.',
  },
  fresh: {
    // Canonical editorial ordering — no persona lean. Equal weights
    // are a no-op against the sort comparator, so the products render
    // in their declared showcase order.
    tagWeights: {},
  },
}

/**
 * Score one product against a persona's tag weights. Returns 0 for the
 * fresh persona or any persona with an empty weight map — in that case
 * callers fall through to the product's natural order.
 */
export function scoreProduct(
  product: BoutiqueProduct,
  weights: Record<string, number>,
): number {
  if (!product.tags || product.tags.length === 0) return 0
  let score = 0
  for (const tag of product.tags) {
    score += weights[tag] ?? 0
  }
  return score
}

/**
 * Stable sort SHOWCASE_PRODUCTS for a given persona. Products with no
 * matching tags keep their original relative order (stable sort), so
 * a persona without a full coverage of the catalog still sees the
 * remainder in a predictable sequence.
 */
export function rankProductsForPersona<T extends BoutiqueProduct>(
  products: readonly T[],
  personaId: string | null | undefined,
): T[] {
  const interests = personaId ? PERSONA_INTERESTS[personaId] : undefined
  if (!interests || Object.keys(interests.tagWeights).length === 0) {
    return [...products]
  }
  // Decorate-sort-undecorate preserves the original index as a
  // tiebreaker, giving a stable sort without needing Array.sort's
  // stability guarantee (which holds in modern engines but is safer
  // made explicit for workshop attendees reading the code).
  const decorated = products.map((p, i) => ({
    product: p,
    score: scoreProduct(p, interests.tagWeights),
    index: i,
  }))
  decorated.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    return a.index - b.index
  })
  return decorated.map(d => d.product)
}

// ---------------------------------------------------------------------
// Editorial cards for "Because you asked..."
//
// Each persona gets a hand-picked set of cards that echo the language
// they'd have used in chat. The fresh persona falls back to the
// canonical generic set (Gifts / Performance / Linen / Home Rituals).
// ---------------------------------------------------------------------

export interface EditorialCard {
  category: string
  title: string
  description: string
}

export const CANONICAL_EDITORIAL: EditorialCard[] = [
  {
    category: 'Gifts',
    title: 'The art of giving well.',
    description:
      'Thoughtful pieces that arrive wrapped in tissue and tied with intention. For the person who notices the details.',
  },
  {
    category: 'Performance and Luxury',
    title: 'Where function meets form.',
    description:
      'Technical fabrics, considered construction. Pieces that perform without announcing it.',
  },
  {
    category: 'Linen Edits',
    title: 'The fabric of slower days.',
    description:
      'Washed, softened, lived-in. Our linen collection gets better with every wear and every wash.',
  },
  {
    category: 'Home Rituals',
    title: 'Objects worth reaching for.',
    description:
      'Ceramic, stoneware, hand-thrown. The everyday pieces that turn a morning routine into a ritual.',
  },
]

export const PERSONA_EDITORIAL: Record<string, EditorialCard[]> = {
  marco: [
    {
      category: 'Weekend escapes',
      title: 'Packed in a single bag.',
      description:
        'Linen that wrinkles honestly, leather that patinas. The pieces that make a 48-hour trip feel unhurried.',
    },
    {
      category: 'Linen edits',
      title: 'Softened by the sun.',
      description:
        'Breathable weaves, warm oat tones. Shirts that earn their golden hour and forgive the rest.',
    },
    {
      category: 'Everyday carry',
      title: 'The weekender, reconsidered.',
      description:
        'Full-grain leather, canvas lining, the quiet kind of heft. A bag that outlasts the trips.',
    },
    {
      category: 'Quiet accessories',
      title: 'Classic, undated.',
      description:
        'Rectangular watches, apothecary notes. Pieces that don’t announce themselves — they just show up.',
    },
  ],
  anna: [
    {
      category: 'Gifting',
      title: 'Wrapped with intention.',
      description:
        'Ceramic, candle, tumbler. Pieces that arrive ready — no last-minute ribbon, no second-guessing.',
    },
    {
      category: 'Milestones',
      title: 'For the occasion that matters.',
      description:
        'Anniversary, housewarming, just-because. Considered objects across every price band.',
    },
    {
      category: 'Home rituals',
      title: 'Everyday beauty, wrapped.',
      description:
        'Sculptural vessels, hand-thrown ceramic. The kind of piece someone actually displays.',
    },
    {
      category: 'Apothecary',
      title: 'Scent, considered.',
      description:
        'Neroli, santal, fig. Small-batch candles and oils that make a gift arrive before it’s opened.',
    },
  ],
  theo: [
    {
      category: 'Slow living',
      title: 'Ritual, not routine.',
      description:
        'Hand-thrown ceramic, washed linen, stoneware tumblers. Objects that reward slowness.',
    },
    {
      category: 'Home rituals',
      title: 'The morning table.',
      description:
        'Woven mats, sculptural vessels. Pieces that make a quiet hour feel intentional.',
    },
    {
      category: 'Wellness',
      title: 'Considered craft.',
      description:
        'Small-batch, artisanal, made in volumes that matter. Pieces with patina, not polish.',
    },
    {
      category: 'Linen edits',
      title: 'Softer with every wash.',
      description:
        'Lounge sets that lean into the weekend. Fabric that loosens around you over seasons.',
    },
  ],
}

/**
 * Resolve the editorial lineup for the active persona, falling back to
 * the canonical set for fresh/unknown personas.
 */
export function editorialForPersona(
  personaId: string | null | undefined,
): EditorialCard[] {
  if (!personaId) return CANONICAL_EDITORIAL
  return PERSONA_EDITORIAL[personaId] ?? CANONICAL_EDITORIAL
}

// ---------------------------------------------------------------------
// Hero suggestion pills — persona-specific "Try asking" queries.
// Each persona sees 5 pills grounded in their interests.
// Fresh visitors see the canonical set.
// ---------------------------------------------------------------------

// Hero pills — the first pill in each persona's list is their
// canonical Turn 1 query, matching the Atelier session fixture
// and the BoutiqueWelcome primary pick. The remaining pills are
// Turn 2/3 follow-ups so the demo flows as one coherent journey.
export const PERSONA_HERO_PILLS: Record<string, string[]> = {
  marco: [
    // Marco's canonical 4-turn workshop demo sequence (+ capstone Turn 5).
    // See lab-content/shared/marco-arc-overview.en.md — these pill
    // strings must match the demo-conversation fixtures exactly.
    // Turn 4 clicks twice per session: once during the opening demo
    // (Stock Keeper stubbed → graceful non-answer), once during the
    // midpoint checkpoint (Stock Keeper wired → real warehouse data).
    'What linen do you have for 10 days in Goa?',            // Turn 1 → Style Advisor · find_pieces
    'What would go with the Hadley shirt?',                  // Turn 2 → Curator + the-packing-list · style_match
    "What's the price range for linen shirts?",              // Turn 3 → Value Analyst · price_intelligence
    'Is the Hadley shirt at the Brooklyn warehouse?',        // Turn 4 → Stock Keeper (stub/wired)
    'What pairs with the Ecru overshirt?',                   // Turn 5 (capstone) → Curator · style_match
  ],
  anna: [
    'A thoughtful gift for someone who loves morning rituals',  // Turn 1
    'Something beautiful under $100',                            // Turn 2
    'Help me pair a candle with something else',                 // Turn 3
    'Wrap-ready gifts with no extra effort',
    'A milestone gift for a new homeowner',
  ],
  theo: [
    'Hand-thrown ceramics for a slower morning routine',  // Turn 1
    'What goes well with the pour-over set?',              // Turn 2
    'Linen pieces that soften over seasons',               // Turn 3
    "My Wabi-Sabi Bowl arrived chipped. Please file a damaged return — my customer id is 'theo'.",  // Turn 4 (Experience Guide payoff)
    // Turn 5 matches Persona Journeys + Boutique welcome P.S. (not the
    // narrower "worth keeping" headline — this is the closet vs home axis).
    'Something for the home, not the wardrobe',
  ],
  fresh: [
    'A thoughtful gift for someone who runs',
    'Pieces for slow Sunday mornings',
    'Something to wear for warm evenings out',
    'Linen pieces that travel well',
    'A cozy layer for cooler nights',
  ],
}

/** Marco Boutique / Atelier Turn 4 — warehouse ask (Stock Keeper · `floor_check`). */
export const MARCO_BUILDER_SESSION_QUERY = PERSONA_HERO_PILLS.marco[3]

export function heroPillsForPersona(
  personaId: string | null | undefined,
): string[] {
  if (!personaId) return PERSONA_HERO_PILLS.fresh
  return PERSONA_HERO_PILLS[personaId] ?? PERSONA_HERO_PILLS.fresh
}

// ---------------------------------------------------------------------
// Featured product ID — the big hero product slot per persona.
// Maps persona → product ID from SHOWCASE_PRODUCTS.
// Fresh visitors see the Nocturne Leather Weekender (id:3 in the
// original lineup; check actual IDs in showcaseProducts.ts).
// ---------------------------------------------------------------------

export const PERSONA_FEATURED_PRODUCT_ID: Record<string, number> = {
  marco: 2,   // Pellier Linen Shirt — Marco's signature linen piece
  anna: 21,    // Beeswax Taper Candles & Fig Candle — gift-forward, wrap-ready
  theo: 31,    // Stoneware Pour-Over Set Woven Mat Set — slow ritual centerpiece
  fresh: 3,   // Nocturne Leather Weekender — editorial hero for new visitors
}

export function featuredProductIdForPersona(
  personaId: string | null | undefined,
): number {
  if (!personaId) return PERSONA_FEATURED_PRODUCT_ID.fresh
  return PERSONA_FEATURED_PRODUCT_ID[personaId] ?? PERSONA_FEATURED_PRODUCT_ID.fresh
}

// ---------------------------------------------------------------------
// Weekend Edit — persona-specific editorial eyebrow + headline + copy.
// The "Weekend, re:defined." block on BoutiquePage swaps entirely
// based on persona so the editorial voice matches the shopper.
// ---------------------------------------------------------------------

export interface WeekendEditContent {
  eyebrow: string
  headline: string
  subheadline: string
}

export const PERSONA_WEEKEND_EDIT: Record<string, WeekendEditContent> = {
  marco: {
    eyebrow: 'The Travel Edit',
    headline: 'Packed light,\nlived fully.',
    subheadline:
      'Linen that softens on the road, leather that earns its patina. A 48-hour wardrobe that never feels rushed.',
  },
  anna: {
    eyebrow: 'The Gift Edit',
    headline: 'Giving,\nre:considered.',
    subheadline:
      'Pieces that arrive wrapped with intention. For the milestone, the just-because, and the person who has everything.',
  },
  theo: {
    eyebrow: 'The Slow Edit',
    headline: 'Ritual,\nnot routine.',
    subheadline:
      'Hand-thrown ceramic, washed linen, stoneware that rewards slowness. The morning table, made intentional.',
  },
  fresh: {
    eyebrow: 'Weekend Edit',
    headline: 'Weekend,\nre:defined.',
    subheadline:
      'Pieces that move with you from morning markets to golden-hour terraces. Linen, leather, ceramic — the weekend wardrobe, considered.',
  },
}

export function weekendEditForPersona(
  personaId: string | null | undefined,
): WeekendEditContent {
  if (!personaId) return PERSONA_WEEKEND_EDIT.fresh
  return PERSONA_WEEKEND_EDIT[personaId] ?? PERSONA_WEEKEND_EDIT.fresh
}

// ---------------------------------------------------------------------
// "Because" chips — a second row of suggestion pills under the hero
// search bar that cite memory or live trends instead of canned queries.
// Each chip carries a `kind` (memory | trend | inventory | weather) and
// the human-readable copy that follows. The hero renders them as
// dashed italic chips with the kind label as a tiny eyebrow.
// ---------------------------------------------------------------------

export type BecauseChipKind = 'memory' | 'trend' | 'inventory' | 'weather'

export interface BecauseChip {
  kind: BecauseChipKind
  /** Human-readable reason, leads with a verb-less clause. */
  text: string
  /** Optional query to fire when the chip is clicked. */
  query?: string
}

export const PERSONA_BECAUSE_CHIPS: Record<string, BecauseChip[]> = {
  marco: [
    {
      kind: 'memory',
      text: 'you saved the Linen Camp Shirt last visit',
      query: 'Show me linen pieces like the Camp Shirt',
    },
    {
      kind: 'trend',
      text: 'terracotta is up 4× this week',
      query: 'Show me terracotta pieces',
    },
  ],
  anna: [
    {
      kind: 'memory',
      text: 'you were shopping for a milestone gift',
      query: 'Thoughtful gifts for a new homeowner',
    },
    {
      kind: 'trend',
      text: 'the Beeswax Tapers restocked an hour ago',
      query: 'Show me the Beeswax Taper Candles',
    },
  ],
  theo: [
    {
      kind: 'memory',
      text: 'you opened the Pour-Over Set twice last week',
      query: 'Pieces that pair with the Pour-Over Set',
    },
    {
      kind: 'inventory',
      text: 'two Wabi-Sabi Bowls just came back in stock',
      query: 'Show me the Wabi-Sabi Bowl',
    },
  ],
  fresh: [
    {
      kind: 'trend',
      text: 'linen searches up 60% since Thursday',
      query: 'Show me trending linen pieces',
    },
    {
      kind: 'inventory',
      text: 'three new arrivals just landed in the Summer Edit',
      query: 'Show me what just arrived',
    },
  ],
}

export function becauseChipsForPersona(
  personaId: string | null | undefined,
): BecauseChip[] {
  if (!personaId) return PERSONA_BECAUSE_CHIPS.fresh
  return PERSONA_BECAUSE_CHIPS[personaId] ?? PERSONA_BECAUSE_CHIPS.fresh
}

// ---------------------------------------------------------------------
// Memory handoff — what the agent "remembers" about a returning shopper.
// Surfaced on the homepage between the hero and the Weekend Edit so
// the most demoable agent capability (durable taste memory) is the
// first thing a returning persona sees. Fresh visitors get a
// learn-as-we-go variant so the layout rhythm stays consistent.
// ---------------------------------------------------------------------

export interface MemoryHandoffItem {
  /** Tool/source label, rendered in mono ("memory.recall", "cart.holds"). */
  tool: string
  /** Plain-language line. */
  text: string
}

export interface MemoryHandoffContent {
  eyebrow: string
  /** Short italic Fraunces title. */
  title: string
  items: MemoryHandoffItem[]
  /** CTA label (defaults to "Pick up where I left off"). */
  cta?: string
}

export const PERSONA_MEMORY_HANDOFF: Record<string, MemoryHandoffContent> = {
  marco: {
    eyebrow: 'Last time you were here · 14 hours ago',
    title: 'You were deciding between two linen pieces. I held them for you.',
    items: [
      { tool: 'memory.recall', text: 'Linen Camp Shirt · size 41 · saved' },
      { tool: 'cart.holds', text: 'Wide-Leg Trouser · in bag, 2 left' },
      { tool: 'inventory.watch', text: 'Slide Sandal · back in 42' },
    ],
  },
  anna: {
    eyebrow: 'Last time you were here · 2 days ago',
    title: 'You were pairing a candle with something to wrap. I kept the shortlist.',
    items: [
      { tool: 'memory.recall', text: 'Beeswax Tapers · saved as gift candidate' },
      { tool: 'pairing.score', text: 'Linen Tea Towel · 0.91 match with the tapers' },
      { tool: 'inventory.watch', text: 'Fig Candle · back in stock today' },
    ],
  },
  theo: {
    eyebrow: 'Last time you were here · 5 days ago',
    title: 'You filed a return on the Wabi-Sabi Bowl. I followed up.',
    items: [
      { tool: 'experience.return', text: 'Bowl · return processed, refund 1–2 days' },
      { tool: 'memory.recall', text: 'Pour-Over Set · opened twice, not yet saved' },
      { tool: 'inventory.watch', text: 'Stoneware Mug · 2 back in stock' },
    ],
  },
  fresh: {
    eyebrow: 'New here · I learn as we go',
    title: "I'll learn your taste as we go. Tell me what you're after.",
    items: [
      { tool: 'memory.seed', text: "I'll remember saved items, sizes, and the queries you return to" },
      { tool: 'inventory.live', text: 'Live stock and restocks, surfaced before you ask' },
      { tool: 'tool.transparency', text: 'Every recommendation cites the source it came from' },
    ],
    cta: 'Try a query',
  },
}

export function memoryHandoffForPersona(
  personaId: string | null | undefined,
): MemoryHandoffContent {
  if (!personaId) return PERSONA_MEMORY_HANDOFF.fresh
  return PERSONA_MEMORY_HANDOFF[personaId] ?? PERSONA_MEMORY_HANDOFF.fresh
}
