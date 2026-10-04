/**
 * One Anna turn, as the backend streams it.
 *
 * The event shapes are the ones `services/chat.py` emits and
 * `tests/test_chat_stream_contract.py` pins: the intent signal, the status
 * line, the Router step, the search step with its server-computed finding
 * and Builder payload, the text deltas, the products and the completion.
 * Used by the screenshot harness in place of a live backend.
 *
 * The numbers come from the repository's own catalog (`data/pellier_catalog.json`,
 * seeded into `pellier.product_catalog`) and the real pipeline's shapes, run
 * against a local Postgres on 2026-10-04 with Anna's plan (under $100, in
 * stock, no candles):
 *
 * - The filter counts are the real aggregate: 31 of 100 are over $100, one of
 *   the rest is sold out (Housewarming Gift Box), four are candles; 64 fit.
 * - The full-text arm is the real `ts_rank_cd` order for
 *   "housewarming | gift | slow | mornings" under those predicates.
 * - The vector arm used a stand-in query vector (the normalized mean of the
 *   catalog's own "slow" shelf embeddings) rather than a Bedrock embedding;
 *   its ranks and similarities are the real cosine order for that vector.
 * - `before` is the real RRF order of the fused 30-row pool, `rrf_score` is
 *   `1/(60 + rank)` summed over the arms, and `after` is a rerank order the
 *   harness fixes so the captures are stable.
 *
 * Every product named is in stock, under $100, carries no candle tag, and
 * shows its own photo.
 */

export const ANNA = {
  id: 'anna',
  display_name: 'Anna Lindqvist',
  role_tag: 'Gift-giver',
  avatar_color: '#6b3d2a',
  avatar_initial: 'A',
  customer_id: 'CUST-ANNA',
  membership: 'circle',
  hero_image: '/assets/personas/anna-720.webp',
  hero_alt: 'Anna at a table set for a housewarming',
  hero_subheadline: 'Gifts, thoughtfully matched.',
  stats: { visits: 6, orders: 5, last_seen_days: 9 },
}

export const ANNA_QUESTION =
  'A housewarming gift for a friend who loves slow mornings. In stock, under $100, and no candles.'

function availability(productId: string) {
  return {
    productId,
    status: 'reconciled_in_stock',
    availableQuantity: 24,
    scope: 'catalog',
    locations: [],
    source: 'warehouse_inventory',
    observedAt: '2026-10-04T14:40:00+00:00',
    catalogCacheQuantity: 24,
    catalogLedgerQuantity: 24,
    aggregateCacheStale: false,
    disagreements: [],
    authority: 'warehouse_inventory',
  }
}

// The three cards the answer names, in the shape `chat.py` emits: catalog
// fields from `_format_products`, availability from `_attach_inventory_evidence`.
const PRODUCTS = [
  { id: '31', name: 'Stoneware Pour-Over Set', brand: 'Pellier', color: 'Ash gray', price: 58, rating: 4.9, reviews: 134, category: 'Kitchen and table', image: '/products/theo-stoneware-pour-over.webp', badge: null, tags: ['ceramic', 'slow', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0, availability: availability('31') },
  { id: '36', name: 'Ceramic Tumblers', brand: 'Pellier', color: 'Speckled charcoal', price: 34, rating: 4.7, reviews: 245, category: 'Kitchen and table', image: '/products/theo-ceramic-tumblers.webp', badge: null, tags: ['ceramic', 'slow', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0, availability: availability('36') },
  { id: '22', name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'White', price: 44, rating: 4.7, reviews: 178, category: 'Kitchen and table', image: '/products/anna-monogrammed-napkins.webp', badge: null, tags: ['linen', 'gift', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0, availability: availability('22') },
]

const ANSWER =
  'For slow mornings, start with the Stoneware Pour-Over Set at $58: a stoneware dripper and carafe in ash gray that brews two cups by hand, so breakfast can take its time. ' +
  'Add the Ceramic Tumblers at $34, a hand-thrown pair in speckled charcoal for juice at breakfast. ' +
  'If they like to host, the Linen Napkins, Set of 4 at $44 arrive gift-boxed and ready to give. ' +
  'All three are in stock and under $100.'

const FINDING = '5 found from 64 that fit under $100 and in stock, candles left out'

const rrf = (fts: number | null, vec: number | null) => (fts ? 1 / (60 + fts) : 0) + (vec ? 1 / (60 + vec) : 0)

const RANKING = {
  available: true,
  rail: 'in-process',
  method: 'hybrid+rerank',
  rrf_k: 60,
  rerank_pool: 15,
  arms: { full_text: 20, vector: 20, fused: 30 },
  filters: { kept: 64, of: 100, removed: { budget: 31, stock: 1, exclusions: 4 } },
  rows: [
    { product_id: '31', name: 'Stoneware Pour-Over Set', fts_rank: null, vec_rank: 1, similarity: 0.773, rrf_score: rrf(null, 1), rerank_score: 0.91, before: 9, after: 1 },
    { product_id: '36', name: 'Ceramic Tumblers', fts_rank: 17, vec_rank: 2, similarity: 0.768, rrf_score: rrf(17, 2), rerank_score: 0.84, before: 2, after: 2 },
    { product_id: '22', name: 'Linen Napkins, Set of 4', fts_rank: 12, vec_rank: 18, similarity: 0.58, rrf_score: rrf(12, 18), rerank_score: 0.72, before: 6, after: 3 },
    { product_id: '37', name: 'Wabi-Sabi Bowl', fts_rank: 13, vec_rank: 4, similarity: 0.717, rrf_score: rrf(13, 4), rerank_score: 0.66, before: 1, after: 4 },
    { product_id: '33', name: 'Olive Wood Cutting Board', fts_rank: 14, vec_rank: 10, similarity: 0.645, rrf_score: rrf(14, 10), rerank_score: 0.58, before: 5, after: 5 },
    { product_id: '65', name: 'Stoneware Mugs, Set of 2', fts_rank: 20, vec_rank: 3, similarity: 0.763, rrf_score: rrf(20, 3), rerank_score: 0.47, before: 4, after: 6 },
    { product_id: '34', name: 'Terracotta Planter', fts_rank: 15, vec_rank: 5, similarity: 0.698, rrf_score: rrf(15, 5), rerank_score: 0.39, before: 3, after: 7 },
    { product_id: '39', name: 'Linen Table Runner', fts_rank: 18, vec_rank: 13, similarity: 0.606, rrf_score: rrf(18, 13), rerank_score: 0.31, before: 7, after: 8 },
  ],
  note: 'Kept counts the hard limits only; the first pass also asks for the preferences the shopper implied, so the fused pool can be smaller',
}

const REQUIREMENTS = { applied: ['under $100', 'in stock', 'no candles'], carried: [] }

const SKILLS = [
  { name: 'the-gift-table', display_name: 'The Gift Table', path: 'skills/the-gift-table/SKILL.md', loaded: 'fixed' },
  { name: 'the-makers-shelf', display_name: "The Maker's Shelf", path: 'skills/the-makers-shelf/SKILL.md', loaded: 'fixed' },
  { name: 'the-packing-list', display_name: 'The Packing List', path: 'skills/the-packing-list/SKILL.md', loaded: 'fixed' },
  { name: 'the-proof-counter', display_name: 'The Proof Counter', path: 'skills/the-proof-counter/SKILL.md', loaded: 'fixed' },
]

function deltas(text: string): object[] {
  return text.split(/(?<=\s)/).map(piece => ({ type: 'content_delta', delta: piece }))
}

export const ANNA_TURN_EVENTS: object[] = [
  { type: 'turn_start', turn_id: 'turn-' + 'a'.repeat(32), session_id: 'session-shots' },
  { type: 'aurora_profile_context', profile: { source: 'Aurora PostgreSQL', customer_id: 'CUST-ANNA', facts_available: 3, orders_available: 5, available: true } },
  { type: 'intent_signal', intent: 'shopping', agent: 'Shopping agent', classifier: 'deterministic', model_family: 'opus', model_id: 'global.anthropic.claude-opus-5' },
  { type: 'status', label: 'Understanding your request' },
  {
    type: 'step', id: 'route', label: 'Understanding your request', status: 'done', finding: 'Sent to the Shopping agent',
    tags: ['Router', 'Memory', 'Skills'],
    builder: { tool: null, rail: 'in-process', intent: 'shopping', agent: 'Shopping agent', model_id: 'global.anthropic.claude-opus-5', skills: SKILLS, skill_mode: 'fixed', memory: { facts: 3, orders: 5, source: 'Aurora PostgreSQL' }, note: null },
  },
  { type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'running', tags: ['Aurora'], builder: { tool: 'search_products' } },
  { type: 'tool_call', tool: 'search_products', status: 'executing' },
  {
    type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', finding: FINDING,
    tags: ['Aurora'],
    builder: { tool: 'search_products', rail: 'in-process', duration_ms: 731, audit_id: 9031, receipt_id: 6, identity: null, ranking: RANKING, requirements: REQUIREMENTS },
  },
  { type: 'tool_call', tool: 'search_products', status: 'completed', duration_ms: 731 },
  { type: 'content_reset' },
  { type: 'status', label: 'Writing your answer' },
  ...deltas(ANSWER),
  ...PRODUCTS.map((product, index) => ({ type: 'product', product, index, total: PRODUCTS.length })),
  {
    type: 'complete',
    response: {
      response: ANSWER,
      products: PRODUCTS,
      suggestions: [],
      success: true,
      rail: 'in-process',
      turn_id: 'turn-' + 'a'.repeat(32),
      session_id: 'session-shots',
      railDecision: { rail: 'in-process', managedRequested: false, available: true, reason: null },
      orchestration: { pattern: 'dispatcher', route: 'shopping', router: 'deterministic', intent: 'shopping', agent: 'Shopping agent', model_id: 'global.anthropic.claude-opus-5', skill_mode: 'fixed', skills: SKILLS },
    },
  },
]

export const ANNA_FINDING = FINDING

export function sseBody(events: object[]): string {
  return events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}
