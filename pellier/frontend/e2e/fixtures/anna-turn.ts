/**
 * One Anna turn, as the backend streams it.
 *
 * The event shapes are the ones `services/chat.py` emits and
 * `tests/test_chat_stream_contract.py` pins: the intent signal, the status
 * line, the Router step, the search step with its server-computed finding
 * and Builder payload, the text deltas, the products and the completion.
 * Used by the screenshot harness in place of a live backend.
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

const PRODUCTS = [
  { id: 65, productId: '65', name: 'Stoneware Mugs, Set of 2', brand: 'Pellier', price: 38, category: 'Kitchen and table', image: '/products/anna-ceramic-bud-vase-480.webp', rating: 4.7, reviews: 212, quantity: 9, inStock: true, availability: { status: 'reconciled_in_stock', availableQuantity: 9 } },
  { id: 22, productId: '22', name: 'Linen Napkins, Set of 4', brand: 'Pellier', price: 44, category: 'Kitchen and table', image: '/products/anna-monogrammed-napkins-480.webp', rating: 4.8, reviews: 148, quantity: 4, inStock: true, availability: { status: 'reconciled_in_stock', availableQuantity: 4 } },
  { id: 27, productId: '27', name: 'Ceramic Bud Vase', brand: 'Pellier', price: 22, category: 'Home', image: '/products/anna-ceramic-bud-vase-480.webp', rating: 4.6, reviews: 96, quantity: 0, inStock: false, availability: { status: 'reconciled_out_of_stock', availableQuantity: 0 } },
]

const ANSWER =
  'For a slow-morning housewarming, start with the Stoneware Mugs, Set of 2 at $38, in a speckled oat glaze with room for a big first coffee. ' +
  'Add the Linen Napkins, Set of 4 at $44 if they like to host; they arrive gift-boxed. ' +
  'The Ceramic Bud Vase at $22 is the small one, though it is sold out just now.'

const RANKING = {
  available: true,
  rail: 'in-process',
  method: 'hybrid+rerank',
  rrf_k: 60,
  rerank_pool: 15,
  arms: { full_text: 12, vector: 20, fused: 23 },
  filters: { kept: 23, of: 100, removed: { budget: 61, stock: 9, exclusions: 4, department: 0 } },
  rows: [
    { product_id: '65', name: 'Stoneware Mugs, Set of 2', fts_rank: 3, vec_rank: 1, similarity: 0.61, rrf_score: 1 / 63 + 1 / 61, rerank_score: 0.84, before: 1, after: 1 },
    { product_id: '22', name: 'Linen Napkins, Set of 4', fts_rank: 1, vec_rank: 5, similarity: 0.52, rrf_score: 1 / 61 + 1 / 65, rerank_score: 0.72, before: 2, after: 2 },
    { product_id: '27', name: 'Ceramic Bud Vase', fts_rank: null, vec_rank: 2, similarity: 0.58, rrf_score: 1 / 62, rerank_score: 0.4, before: 5, after: 3 },
    { product_id: '36', name: 'Ceramic Tumblers', fts_rank: 6, vec_rank: 3, similarity: 0.57, rrf_score: 1 / 66 + 1 / 63, rerank_score: 0.38, before: 3, after: 4 },
    { product_id: '72', name: 'Espresso Cups, Set of 4', fts_rank: 2, vec_rank: 8, similarity: 0.49, rrf_score: 1 / 62 + 1 / 68, rerank_score: 0.35, before: 4, after: 5 },
    { product_id: '31', name: 'Stoneware Pour-Over Set', fts_rank: 4, vec_rank: 4, similarity: 0.55, rrf_score: 1 / 64 + 1 / 64, rerank_score: 0.31, before: 6, after: 6 },
    { product_id: '66', name: 'Glass Carafe', fts_rank: 9, vec_rank: 6, similarity: 0.5, rrf_score: 1 / 69 + 1 / 66, rerank_score: 0.22, before: 7, after: 7 },
    { product_id: '39', name: 'Linen Table Runner', fts_rank: 5, vec_rank: null, similarity: null, rrf_score: 1 / 65, rerank_score: 0.18, before: 8, after: 8 },
  ],
}

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
    type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', finding: '3 under $100 and in stock, candles left out',
    tags: ['Aurora'],
    builder: { tool: 'search_products', rail: 'in-process', duration_ms: 184, audit_id: 9031, receipt_id: 412, identity: null, ranking: RANKING },
  },
  { type: 'tool_call', tool: 'search_products', status: 'completed', duration_ms: 184 },
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

export function sseBody(events: object[]): string {
  return events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}
