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
 * seeded into `pellier.product_catalog`) and the pipeline's own queries, run
 * against a local Postgres on 2026-10-04 with Anna's plan (under $100, in
 * stock, no candles; `price <= 100 AND quantity > 0 AND NOT (tags ?| '{candle}'
 * OR materials ?| '{candle}')`):
 *
 * - The filter counts are the real aggregate: 31 of 100 are over $100, one of
 *   the rest is sold out (Housewarming Gift Box), four are candles; 64 fit.
 * - `FULL_TEXT_ARM` is `store_tools.fts_branch_sql` as it ran: `ts_rank_cd`
 *   order for `to_tsquery('english', 'housewarming | gift | slow | mornings')`
 *   under those predicates, 20 rows. Equal scores keep the order Postgres
 *   returned them in.
 * - `VECTOR_ARM` is `store_tools.vector_branch_sql` with a stand-in query
 *   vector, the mean of the catalog embeddings of the products tagged `slow`
 *   (no Bedrock embedding was made); its ranks and cosine similarities are
 *   the real order for that vector, 20 rows.
 * - The fused pool, each row's ranks, `rrf_score` and `before` are derived
 *   here by `rrfMerge`, a transcription of `store_tools.rrf_merge`, from
 *   those two arms. Nothing below is typed by hand except the rerank order,
 *   which the harness fixes so the captures are stable (no Cohere call).
 *
 * Every product named is in stock, under $100, carries no candle tag, and
 * shows its own photo.
 *
 * The search step also carries `results`, what the storefront grid draws: the
 * result order (`ANNA_RESULT_IDS`, the reranked rows, then the rest of the
 * fused pool in RRF order, at most 30) and its size, the limits as tags and
 * the same filter counts. `anna-cards.ts` holds the cards for those ids.
 */

export const ANNA = {
  id: 'anna',
  display_name: 'Anna Lindqvist',
  role_tag: 'Gift-giver',
  avatar_color: '#6b3d2a',
  avatar_initial: 'A',
  customer_id: 'CUST-ANNA',
  edit: 'anna',
  hero_image: '/assets/personas/anna-720.webp',
  hero_alt: 'A white gift box tied with a blush-pink ribbon, a blank kraft tag and a vase with one eucalyptus stem on a small oak side table',
  hero_subheadline: 'Gifts, thoughtfully matched.',
  stats: { visits: 6, orders: 5, last_seen_days: 9 },
}

export const ANNA_QUESTION =
  'A housewarming gift for a friend who loves slow mornings. In stock, under $100, and no candles.'

// The three cards the answer names, in the shape `chat.py` emits: catalog
// fields from `_format_products`, stock from `_attach_stock`.
const PRODUCTS = [
  { id: '31', name: 'Stoneware Pour-Over Set', brand: 'Pellier', color: 'Ash gray', price: 58, rating: 4.9, reviews: 134, category: 'Kitchen and table', image: '/products/theo-stoneware-pour-over-set.webp', badge: null, tags: ['ceramic', 'slow', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0 },
  { id: '36', name: 'Ceramic Tumblers', brand: 'Pellier', color: 'Speckled charcoal', price: 34, rating: 4.7, reviews: 245, category: 'Kitchen and table', image: '/products/theo-ceramic-tumblers.webp', badge: null, tags: ['ceramic', 'slow', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0 },
  { id: '22', name: 'Linen Napkins, Set of 4', brand: 'Pellier', color: 'White', price: 44, rating: 4.7, reviews: 178, category: 'Kitchen and table', image: '/products/anna-linen-napkins.webp', badge: null, tags: ['linen', 'gift', 'home'], ownership: null, quantity: 24, inStock: true, originalPrice: null, discountPercent: 0 },
]

const ANSWER =
  'For slow mornings, start with the Stoneware Pour-Over Set at $58: a stoneware dripper and carafe in ash gray that brews two cups by hand, so breakfast can take its time. ' +
  'Add the Ceramic Tumblers at $34, a hand-thrown pair in speckled charcoal for juice at breakfast. ' +
  'If they like to host, the Linen Napkins, Set of 4 at $44 arrive gift-boxed and ready to give. ' +
  'All three are in stock and under $100.'

const FINDING = '5 found from 64 that fit under $100 and in stock, candles left out'

export const RRF_K = 60
export const RERANK_POOL = 15

/** The full-text arm: product id and name, in `ts_rank_cd` order. */
export const FULL_TEXT_ARM: ReadonlyArray<readonly [string, string]> = [
  ['30', 'Gift Wrapping Kit'],
  ['90', 'Morning Run Shorts'],
  ['28', 'Leather Journal'],
  ['78', 'Linen Photo Album'],
  ['76', 'Greeting Card Set'],
  ['77', 'Recycled Wrapping Paper'],
  ['73', 'Dot-Grid Notebook Set'],
  ['74', 'Brass Pen'],
  ['75', 'Leather Desk Tray'],
  ['83', 'Woven Storage Baskets'],
  ['62', 'Leather Watch Roll'],
  ['22', 'Linen Napkins, Set of 4'],
  ['37', 'Wabi-Sabi Bowl'],
  ['33', 'Olive Wood Cutting Board'],
  ['34', 'Terracotta Planter'],
  ['35', 'Brass Incense Holder'],
  ['36', 'Ceramic Tumblers'],
  ['39', 'Linen Table Runner'],
  ['40', 'Charcoal Soap Bar'],
  ['65', 'Stoneware Mugs, Set of 2'],
]

/** The vector arm: product id, name and cosine similarity, in distance order. */
export const VECTOR_ARM: ReadonlyArray<readonly [string, string, number]> = [
  ['31', 'Stoneware Pour-Over Set', 0.768],
  ['36', 'Ceramic Tumblers', 0.764],
  ['65', 'Stoneware Mugs, Set of 2', 0.757],
  ['37', 'Wabi-Sabi Bowl', 0.716],
  ['34', 'Terracotta Planter', 0.696],
  ['67', 'Salt Cellar with Spoon', 0.696],
  ['72', 'Espresso Cups, Set of 4', 0.681],
  ['66', 'Glass Carafe', 0.652],
  ['1', 'Tall Stoneware Vase', 0.648],
  ['71', 'Wooden Salad Servers', 0.647],
  ['33', 'Olive Wood Cutting Board', 0.642],
  ['27', 'Ceramic Bud Vase', 0.634],
  ['39', 'Linen Table Runner', 0.604],
  ['35', 'Brass Incense Holder', 0.602],
  ['23', 'Ceramic Ring Dish', 0.598],
  ['7', 'Jute Placemats, Set of 4', 0.595],
  ['41', 'Coral Lacquer Catchall', 0.591],
  ['22', 'Linen Napkins, Set of 4', 0.585],
  ['88', 'Everyday Chinos', 0.559],
  ['26', 'Handmade Soap Set', 0.554],
]

export interface FusedRow {
  product_id: string
  name: string
  fts_rank: number | null
  vec_rank: number | null
  similarity: number | null
  rrf_score: number
}

/**
 * `store_tools.rrf_merge`: sum `1 / (k + rank)` over both arms. Vector rows
 * enter first and keep their similarity; the sort is stable, so an equal
 * score keeps that order, as the pipeline's does.
 */
export function rrfMerge(
  vectorArm: ReadonlyArray<readonly [string, string, number]>,
  fullTextArm: ReadonlyArray<readonly [string, string]>,
  k: number,
): FusedRow[] {
  const rows = new Map<string, FusedRow>()
  vectorArm.forEach(([id, name, similarity], index) => {
    rows.set(id, { product_id: id, name, fts_rank: null, vec_rank: index + 1, similarity, rrf_score: 1 / (k + index + 1) })
  })
  fullTextArm.forEach(([id, name], index) => {
    const row = rows.get(id) ?? { product_id: id, name, fts_rank: null, vec_rank: null, similarity: null, rrf_score: 0 }
    row.fts_rank = index + 1
    row.rrf_score += 1 / (k + index + 1)
    rows.set(id, row)
  })
  return Array.from(rows.values()).sort((a, b) => b.rrf_score - a.rrf_score)
}

/** The fused pool in RRF order; a row's position here is its `before`. */
export const FUSED = rrfMerge(VECTOR_ARM, FULL_TEXT_ARM, RRF_K)

/** The final order after rerank, fixed by hand for stable captures, with its scores. */
export const RERANKED: ReadonlyArray<readonly [string, number]> = [
  ['31', 0.91],
  ['36', 0.84],
  ['22', 0.72],
  ['37', 0.66],
  ['33', 0.58],
  ['65', 0.47],
  ['34', 0.39],
  ['39', 0.31],
]

// `moved` is what `ranking_evidence.ranking_from_execution` sends: before minus after.
const RANKING_ROWS = RERANKED.map(([id, rerank_score], index) => {
  const before = FUSED.findIndex(row => row.product_id === id) + 1
  if (before === 0) throw new Error(`reranked product ${id} is not in the fused pool`)
  return { ...FUSED[before - 1], rerank_score, before, after: index + 1, moved: before - (index + 1) }
})

const RANKING = {
  available: true,
  rail: 'in-process',
  method: 'hybrid+rerank',
  rrf_k: RRF_K,
  rerank_pool: RERANK_POOL,
  arms: { full_text: FULL_TEXT_ARM.length, vector: VECTOR_ARM.length, fused: FUSED.length },
  filters: {
    kept: 64,
    of: 100,
    removed: { budget: 31, stock: 1, exclusions: 4 },
    excluded: [{ value: 'candle', count: 4, noun: 'candles' }],
  },
  rows: RANKING_ROWS,
  note: 'Kept counts only the hard limits, so the fused pool can be smaller.',
}

export const ANNA_RANKING = RANKING

/** The grid's order: the reranked rows, then the rest of the fused pool in RRF order. */
export const ANNA_RESULT_IDS: readonly string[] = [
  ...RERANKED.map(([id]) => id),
  ...FUSED.map(row => row.product_id).filter(id => !RERANKED.some(([reranked]) => reranked === id)),
].slice(0, 30)

const RESULTS = {
  available: true,
  rail: 'in-process',
  product_ids: ANNA_RESULT_IDS,
  count: ANNA_RESULT_IDS.length,
  limits: [
    { kind: 'budget', label: 'Under $100', origin: 'stated' },
    { kind: 'stock', label: 'In stock', origin: 'stated' },
    { kind: 'exclusions', value: 'candle', label: 'No candles', origin: 'stated' },
  ],
  filters: RANKING.filters,
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

const ROUTE_BUILDER = {
  tool: null, rail: 'in-process', intent: 'shopping', agent: 'Shopping agent',
  model_id: 'global.anthropic.claude-opus-5', skills: SKILLS, skill_mode: 'fixed',
  memory: { facts: 1, orders: 5, source: 'Aurora PostgreSQL' },
  grant: { tools: ['search_products', 'browse_department', 'compare_products'], rule: null },
  note: null,
}

export const ANNA_TURN_EVENTS: object[] = [
  {
    type: 'turn_start', turn_id: 'turn-' + 'a'.repeat(32), session_id: 'session-shots',
    principal: { authenticated: true, customerId: 'CUST-ANNA', signInMethod: 'workshop' },
  },
  { type: 'aurora_profile_context', profile: { source: 'Aurora PostgreSQL', customer_id: 'CUST-ANNA', facts_available: 1, orders_available: 5, available: true } },
  { type: 'intent_signal', intent: 'shopping', agent: 'Shopping agent', classifier: 'deterministic', model_family: 'opus', model_id: 'global.anthropic.claude-opus-5' },
  { type: 'status', label: 'Understanding your request' },
  {
    type: 'step', id: 'route', label: 'Understanding your request', status: 'done', finding: 'Sent to the Shopping agent',
    tags: ['Router', 'Memory', 'Skills'],
    builder: { ...ROUTE_BUILDER, stop_reason: null },
  },
  { type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'running', tags: ['Aurora'], builder: { tool: 'search_products' } },
  { type: 'tool_call', tool: 'search_products', status: 'executing' },
  {
    type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'done', finding: FINDING,
    tags: ['Aurora'],
    builder: { tool: 'search_products', rail: 'in-process', duration_ms: 731, audit_id: 9031, receipt_id: 6, identity: null, ranking: RANKING, requirements: REQUIREMENTS },
    results: RESULTS,
  },
  { type: 'tool_call', tool: 'search_products', status: 'completed', duration_ms: 731 },
  { type: 'content_reset' },
  { type: 'status', label: 'Writing your answer' },
  ...deltas(ANSWER),
  ...PRODUCTS.map((product, index) => ({ type: 'product', product, index, total: PRODUCTS.length })),
  // The Router step again, with how the turn ended, as `chat.py` sends it.
  {
    type: 'step', id: 'route', label: 'Understanding your request', status: 'done', finding: 'Sent to the Shopping agent',
    tags: ['Router', 'Memory', 'Skills'],
    builder: { ...ROUTE_BUILDER, stop_reason: 'end_turn' },
  },
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
      orchestration: { pattern: 'dispatcher', route: 'shopping', router: 'deterministic', intent: 'shopping', agent: 'Shopping agent', model_id: 'global.anthropic.claude-opus-5', skill_mode: 'fixed', skills: SKILLS, stop_reason: 'end_turn' },
    },
  },
]

export const ANNA_FINDING = FINDING

/** The answer's cards, in the order it names them: they lead the page grid. */
export const ANNA_PICKS: readonly string[] = ['31', '36', '22']

/** Anna's session, as `/api/auth/me` reports it after the chooser signed her in. */
export const ANNA_ME = {
  user_id: 'sub-anna',
  email: 'anna@pellier.example.com',
  given_name: 'anna',
  username: 'anna',
  sign_in_method: 'workshop',
}

export function sseBody(events: object[]): string {
  return events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}
