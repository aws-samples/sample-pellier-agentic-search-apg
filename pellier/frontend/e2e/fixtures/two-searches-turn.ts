/**
 * Two searches at once, as the backend streams them: the Builder view's case.
 *
 * Both search payloads are recorded, neither is typed by hand:
 *
 * - The linen search (`step-1` here) is a live turn recorded on 2026-10-05
 *   from a scratch backend on this branch against `pellier_fourlab_c3` with
 *   live Bedrock ("Hadley Linen Shirt, under $100, no wool"): its finding,
 *   ranking rows, result ids, limits and filter counts are exactly what the
 *   stream carried. `HADLEY_RESULT_CARDS` are the cards
 *   `GET /api/products?ids=` returned for those ids on the same run.
 * - The housewarming search (`step-2`) is Anna's recorded search from
 *   `anna-turn.ts`.
 *
 * What is scripted: the two run as one turn, `step-2` finishes first, and
 * the answer names the Hadley Linen Shirt, the Italian Linen Camp Shirt and
 * the Stoneware Pour-Over Set. Each step carries only its own evidence, as
 * the backend now keys evidence by tool use, so the page shows the linen
 * search (it holds two of the named pieces) and the dock shows two search
 * steps, each with its own "How it ranked".
 */
import { ANNA_TURN_EVENTS } from './anna-turn'

export const TWO_SEARCHES_QUESTION =
  'A linen shirt under $100 with no wool, and a housewarming gift for a friend who loves slow mornings, in stock, under $100, no candles.'

/** The recorded linen search, as its done step event streamed. */
const LINEN_SEARCH_DONE = {"type": "step", "id": "step-1", "label": "Searching the catalog in Aurora", "status": "done", "finding": "5 found from 67 that fit under $100, wool left out", "tags": ["Aurora"], "builder": {"tool": "search_products", "rail": "in-process", "duration_ms": 2295, "audit_id": 25, "receipt_id": 18, "identity": null, "ranking": {"available": true, "rail": "in-process", "method": "hybrid+rerank", "rrf_k": 60, "rerank_pool": 15, "arms": {"full_text": 10, "vector": 10, "fused": 10}, "filters": {"kept": 67, "of": 100, "removed": {"budget": 31, "exclusions": 2}, "excluded": [{"value": "wool", "count": 2, "noun": "wool"}]}, "rows": [{"product_id": "2", "name": "Hadley Linen Shirt", "fts_rank": 1, "vec_rank": 1, "similarity": 0.6158096147151048, "rrf_score": 0.03278688524590164, "rerank_score": 0.8242501616477966, "before": 1, "after": 1, "moved": 0}, {"product_id": "16", "name": "Linen Overshirt", "fts_rank": 6, "vec_rank": 2, "similarity": 0.44828055233707165, "rrf_score": 0.03128054740957967, "rerank_score": 0.20348620414733887, "before": 3, "after": 2, "moved": 1}, {"product_id": "11", "name": "Italian Linen Camp Shirt", "fts_rank": 2, "vec_rank": 3, "similarity": 0.4475054451093117, "rrf_score": 0.03200204813108039, "rerank_score": 0.16361939907073975, "before": 2, "after": 3, "moved": -1}, {"product_id": "18", "name": "Cotton-Linen Crew Tee", "fts_rank": 5, "vec_rank": 4, "similarity": 0.4433024691551206, "rrf_score": 0.031009615384615385, "rerank_score": 0.15784983336925507, "before": 4, "after": 4, "moved": 0}, {"product_id": "14", "name": "Linen Drawstring Trousers", "fts_rank": 4, "vec_rank": 5, "similarity": 0.33278933177185144, "rrf_score": 0.031009615384615385, "rerank_score": 0.056076012551784515, "before": 5, "after": 5, "moved": 0}, {"product_id": "70", "name": "100% Linen Apron", "fts_rank": 10, "vec_rank": 6, "similarity": 0.3177053223672752, "rrf_score": 0.029437229437229435, "rerank_score": 0.04924507066607475, "before": 7, "after": 6, "moved": 1}, {"product_id": "22", "name": "Linen Napkins, Set of 4", "fts_rank": 7, "vec_rank": 9, "similarity": 0.2940858006477377, "rrf_score": 0.029418126757516764, "rerank_score": 0.03749928995966911, "before": 8, "after": 7, "moved": 1}, {"product_id": "78", "name": "Linen Photo Album", "fts_rank": 9, "vec_rank": 10, "similarity": 0.2522845117876229, "rrf_score": 0.02877846790890269, "rerank_score": 0.03114684484899044, "before": 10, "after": 8, "moved": 2}], "note": "Kept counts only the hard limits, so the fused pool can be smaller."}, "requirements": {"applied": ["under $100", "no wool"], "carried": []}}, "results": {"available": true, "rail": "in-process", "product_ids": ["2", "16", "11", "18", "14", "70", "22", "78", "39", "82"], "count": 10, "limits": [{"kind": "budget", "label": "Under $100", "origin": "stated"}, {"kind": "exclusions", "value": "wool", "label": "No wool", "origin": "stated"}], "filters": {"kept": 67, "of": 100, "removed": {"budget": 31, "exclusions": 2}, "excluded": [{"value": "wool", "count": 2, "noun": "wool"}]}}}

/** The cards for the linen search's ids, as `GET /api/products?ids=` returned them. */
export const HADLEY_RESULT_CARDS = [{"id": 2, "brand": "Hadley", "name": "Hadley Linen Shirt", "color": "Ivory", "price": 78.0, "rating": 4.8, "reviewCount": 312, "category": "Clothing", "imageUrl": "/products/fresh-hadley-linen-shirt.webp", "badge": "EDITORS_PICK", "tags": ["linen", "everyday", "minimal", "neutral"], "reasoning": null, "quantity": 20, "warehouses": [{"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 14, "shipWindowMin": 3, "shipWindowMax": 5}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 6, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 0, "shipWindowMin": 1, "shipWindowMax": 2}]}, {"id": 16, "brand": "Pellier", "name": "Linen Overshirt", "color": "Sage green", "price": 88.0, "rating": 4.7, "reviewCount": 143, "category": "Clothing", "imageUrl": "/products/marco-linen-overshirt.webp", "badge": "EDITORS_PICK", "tags": ["linen", "travel", "everyday"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 10, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 7, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 11, "brand": "Pellier", "name": "Italian Linen Camp Shirt", "color": "Indigo", "price": 68.0, "rating": 4.8, "reviewCount": 287, "category": "Clothing", "imageUrl": "/products/marco-italian-linen-camp-shirt.webp", "badge": "BESTSELLER", "tags": ["linen", "travel", "resort"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 10, "shipWindowMin": 3, "shipWindowMax": 5}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 7, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 7, "shipWindowMin": 1, "shipWindowMax": 2}]}, {"id": 18, "brand": "Pellier", "name": "Cotton-Linen Crew Tee", "color": "Cream", "price": 26.0, "rating": 4.5, "reviewCount": 412, "category": "Clothing", "imageUrl": "/products/marco-cotton-linen-crew-tee.webp", "badge": null, "tags": ["linen", "travel", "everyday", "minimal"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 10, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 7, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 14, "brand": "Pellier", "name": "Linen Drawstring Trousers", "color": "Oat", "price": 78.0, "rating": 4.7, "reviewCount": 225, "category": "Clothing", "imageUrl": "/products/marco-linen-drawstring-trousers.webp", "badge": null, "tags": ["linen", "travel", "resort", "neutral"], "reasoning": null, "quantity": 5, "warehouses": [{"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 3, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 2, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 0, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 70, "brand": "EcoThread", "name": "100% Linen Apron", "color": "Flax", "price": 44.0, "rating": 4.6, "reviewCount": 119, "category": "Kitchen and table", "imageUrl": "/products/fresh-linen-apron.webp", "badge": null, "tags": ["linen", "home", "everyday"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 10, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 7, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 22, "brand": "Pellier", "name": "Linen Napkins, Set of 4", "color": "White", "price": 44.0, "rating": 4.7, "reviewCount": 178, "category": "Kitchen and table", "imageUrl": "/products/anna-linen-napkins.webp", "badge": null, "tags": ["linen", "gift", "home"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 10, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 7, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 78, "brand": "Pellier", "name": "Linen Photo Album", "color": "Oatmeal", "price": 56.0, "rating": 4.7, "reviewCount": 71, "category": "Stationery and gifts", "imageUrl": "/products/anna-linen-photo-album.webp", "badge": null, "tags": ["linen", "gift", "classic"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 10, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 7, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 39, "brand": "EcoThread", "name": "Linen Table Runner", "color": "Flax", "price": 42.0, "rating": 4.7, "reviewCount": 178, "category": "Kitchen and table", "imageUrl": "/products/theo-linen-table-runner.webp", "badge": "JUST_IN", "tags": ["linen", "slow", "home", "neutral"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 10, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 7, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}, {"id": 82, "brand": "EcoThread", "name": "Linen Cushion Covers, Set of 2", "color": "Rust and oat", "price": 52.0, "rating": 4.6, "reviewCount": 127, "category": "Home", "imageUrl": "/products/house-linen-cushion-covers.webp", "badge": null, "tags": ["linen", "home", "warm"], "reasoning": null, "quantity": 24, "warehouses": [{"warehouseId": "ATX-02", "name": "Austin", "city": "Austin, TX", "quantity": 10, "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "name": "Brooklyn", "city": "Brooklyn, NY", "quantity": 7, "shipWindowMin": 1, "shipWindowMax": 2}, {"warehouseId": "PDX-01", "name": "Portland", "city": "Portland, OR", "quantity": 7, "shipWindowMin": 3, "shipWindowMax": 5}]}]

interface StreamEvent {
  type: string
  id?: string
  status?: string
  product?: { id: string }
  response?: Record<string, unknown>
}

const anna = ANNA_TURN_EVENTS as StreamEvent[]
const annaSearchDone = anna.find(event => event.type === 'step' && event.id === 'step-1' && event.status === 'done')
if (!annaSearchDone) throw new Error("anna-turn.ts lost its search step")
const route = anna.find(event => event.type === 'step' && event.id === 'route')
const opening = anna.slice(0, anna.indexOf(route as StreamEvent) + 1)
const turnEnd = anna.find(event => event.type === 'complete')
if (!turnEnd?.response) throw new Error('anna-turn.ts lost its completion')

const SEARCH_RUNNING = { type: 'step', label: 'Searching the catalog in Aurora', status: 'running', tags: ['Aurora'], builder: { tool: 'search_products' } }

const pourOver = anna.find(event => event.type === 'product' && event.product?.id === '31')?.product
if (!pourOver) throw new Error('anna-turn.ts lost the Stoneware Pour-Over Set')

const PRODUCTS = [
  {"id": "2", "name": "Hadley Linen Shirt", "brand": "Hadley", "color": "Ivory", "price": 78.0, "rating": 4.8, "reviews": 312, "category": "Clothing", "image": "/products/fresh-hadley-linen-shirt.webp", "badge": "EDITORS_PICK", "tags": ["linen", "everyday", "minimal", "neutral"], "ownership": null, "quantity": 20, "inStock": true, "originalPrice": null, "discountPercent": 0, "availability": {"productId": "2", "status": "reconciled_in_stock", "availableQuantity": 20, "scope": "warehouse", "locations": [{"warehouseId": "PDX-01", "quantity": 14, "cacheQuantity": 14, "ledgerQuantity": 14, "displayName": "Portland", "city": "Portland, OR", "shipWindowMin": 3, "shipWindowMax": 5}, {"warehouseId": "ATX-02", "quantity": 6, "cacheQuantity": 6, "ledgerQuantity": 6, "displayName": "Austin", "city": "Austin, TX", "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "quantity": 0, "cacheQuantity": 0, "ledgerQuantity": 0, "displayName": "Brooklyn", "city": "Brooklyn, NY", "shipWindowMin": 1, "shipWindowMax": 2}], "source": "pellier.inventory_ledger", "observedAt": "2026-10-05T04:32:38.074297+00:00", "catalogCacheQuantity": 20, "catalogLedgerQuantity": 20, "aggregateCacheStale": false, "disagreements": [], "authority": "source_of_truth", "reconciledToLedger": true, "note": "", "isReconciled": true, "isObserved": false, "supportsAvailabilityClaim": true}},
  {"id": "11", "name": "Italian Linen Camp Shirt", "brand": "Pellier", "color": "Indigo", "price": 68.0, "rating": 4.8, "reviews": 287, "category": "Clothing", "image": "/products/marco-italian-linen-camp-shirt.webp", "badge": "BESTSELLER", "tags": ["linen", "travel", "resort"], "ownership": null, "quantity": 24, "inStock": true, "originalPrice": null, "discountPercent": 0, "availability": {"productId": "11", "status": "reconciled_in_stock", "availableQuantity": 24, "scope": "warehouse", "locations": [{"warehouseId": "PDX-01", "quantity": 10, "cacheQuantity": 10, "ledgerQuantity": 10, "displayName": "Portland", "city": "Portland, OR", "shipWindowMin": 3, "shipWindowMax": 5}, {"warehouseId": "ATX-02", "quantity": 7, "cacheQuantity": 7, "ledgerQuantity": 7, "displayName": "Austin", "city": "Austin, TX", "shipWindowMin": 2, "shipWindowMax": 4}, {"warehouseId": "BK-01", "quantity": 7, "cacheQuantity": 7, "ledgerQuantity": 7, "displayName": "Brooklyn", "city": "Brooklyn, NY", "shipWindowMin": 1, "shipWindowMax": 2}], "source": "pellier.inventory_ledger", "observedAt": "2026-10-05T04:32:38.074310+00:00", "catalogCacheQuantity": 24, "catalogLedgerQuantity": 24, "aggregateCacheStale": false, "disagreements": [], "authority": "source_of_truth", "reconciledToLedger": true, "note": "", "isReconciled": true, "isObserved": false, "supportsAvailabilityClaim": true}},
  pourOver,
]

const ANSWER =
  'For the shirt, the Hadley Linen Shirt at $78 is the one: relaxed ivory linen with shell buttons. ' +
  'The Italian Linen Camp Shirt at $68 is a short-sleeve alternative in deep indigo. ' +
  'For the housewarming, the Stoneware Pour-Over Set at $58 brews two cups by hand, so breakfast can take its time.'

function deltas(text: string): object[] {
  return text.split(/(?<=\s)/).map(piece => ({ type: 'content_delta', delta: piece }))
}

export const TWO_SEARCHES_EVENTS: object[] = [
  ...opening,
  { ...SEARCH_RUNNING, id: 'step-1' },
  { type: 'tool_call', tool: 'search_products', status: 'executing' },
  { ...SEARCH_RUNNING, id: 'step-2' },
  // The housewarming search finishes first; each step carries only its own evidence.
  { ...annaSearchDone, id: 'step-2' },
  { type: 'tool_call', tool: 'search_products', status: 'completed', duration_ms: 731 },
  LINEN_SEARCH_DONE,
  { type: 'tool_call', tool: 'search_products', status: 'completed', duration_ms: 2295 },
  { type: 'content_reset' },
  { type: 'status', label: 'Writing your answer' },
  ...deltas(ANSWER),
  ...PRODUCTS.map((product, index) => ({ type: 'product', product, index, total: PRODUCTS.length })),
  { ...turnEnd, response: { ...turnEnd.response, response: ANSWER, products: PRODUCTS } },
]
