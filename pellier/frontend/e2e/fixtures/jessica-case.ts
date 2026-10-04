/**
 * Jessica's case as the desk's API returns it, for the recorded screenshots.
 *
 * The numbers are the seed's: the Waffle Bath Robe, Sage ($64) and the Reed
 * Diffuser ($36) went back, 10000 cents together, no credit recorded. The
 * investigation stream carries the same `step` shape `services/operator_graph.py`
 * emits, with the findings its templates compute.
 */

export const ACTION_HASH = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90'
export const WRITE_KEY = `operator-review:41:${ACTION_HASH.slice(0, 32)}`

export const NADIA_ME = {
  user_id: 'sub-nadia',
  email: 'nadia@pellier.example.com',
  given_name: 'nadia',
  username: 'nadia',
  sign_in_method: 'cognito',
}

export const BOOK = {
  clients: [
    { customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura', personaId: 'jessica', openRequests: 1, openRequest: 'Two items went back, no credit yet', openRequestStatus: 'open', lastOrder: { productName: 'Waffle Bath Robe, Sage', placedAt: '2026-08-31T10:00:00Z' } },
    { customerId: 'CUST-THEO', slug: 'theo', name: 'Theo Lindqvist', personaId: 'theo', openRequests: 1, openRequest: 'Wabi-Sabi Bowl arrived chipped', openRequestStatus: 'open', lastOrder: { productName: 'Wabi-Sabi Bowl', placedAt: '2026-09-28T10:00:00Z' } },
    { customerId: 'CUST-ANNA', slug: 'anna', name: 'Anna Berg', personaId: 'anna', openRequests: 0, openRequest: null, openRequestStatus: null, lastOrder: { productName: 'Stoneware Pour-Over Set', placedAt: '2026-09-12T10:00:00Z' } },
    { customerId: 'CUST-MARCO', slug: 'marco', name: 'Marco Delgado', personaId: 'marco', openRequests: 0, openRequest: null, openRequestStatus: null, lastOrder: { productName: 'Hadley Linen Shirt', placedAt: '2026-09-20T10:00:00Z' } },
  ],
  total: 4,
  openRequests: 2,
}

const ORDERS = [
  { orderId: 301, productId: '42', productName: 'Waffle Bath Robe, Sage', brand: 'NestWell', amountPaidCents: 6400, amountPaid: '64.00', quantity: 1, placedAt: '2026-08-31T10:00:00Z', imageUrl: '/products/house-waffle-bath-robe-sage.png', returnStatus: 'approved', returned: true },
  { orderId: 302, productId: '25', productName: 'Reed Diffuser', brand: 'Pellier', amountPaidCents: 3600, amountPaid: '36.00', quantity: 1, placedAt: '2026-08-31T10:00:00Z', imageUrl: '/products/anna-reed-diffuser.png', returnStatus: 'approved', returned: true },
  { orderId: 303, productId: '31', productName: 'Stoneware Pour-Over Set', brand: 'Pellier', amountPaidCents: 5800, amountPaid: '58.00', quantity: 1, placedAt: '2026-06-06T10:00:00Z', imageUrl: '/products/theo-stoneware-pour-over-set.png', returnStatus: null, returned: false },
  { orderId: 304, productId: '43', productName: 'Quilted Silk Vest', brand: 'Pellier', amountPaidCents: 12900, amountPaid: '129.00', quantity: 1, placedAt: '2026-03-08T10:00:00Z', imageUrl: '/products/house-quilted-silk-vest.png', returnStatus: null, returned: false },
  { orderId: 305, productId: '50', productName: 'Oat Merino Crew', brand: 'EcoThread', amountPaidCents: 10800, amountPaid: '108.00', quantity: 1, placedAt: '2025-12-08T10:00:00Z', imageUrl: '/products/house-oat-merino-crew.png', returnStatus: null, returned: false },
]

export const RECORD = {
  dataSource: 'Local PostgreSQL',
  client: { customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura', personaId: 'jessica', openTicketCount: 1, returnedCount: 2, creditBalanceCents: 0, creditBalance: '0.00' },
  orders: ORDERS,
  tickets: [{
    ticketId: 'TKT-2026-3015', subject: 'Two items went back, no credit yet', status: 'open', channel: 'chat',
    lastNote: 'Sent back the Waffle Bath Robe, Sage and the Reed Diffuser last week. Both were received. No store credit has been recorded.',
    openedAt: '2026-09-26T10:00:00Z', resolvedAt: null,
  }],
  credits: [],
  reviews: [] as unknown[],
}

const BASE_REVIEW = {
  reviewId: 41, customerId: 'CUST-JESSICA', customerName: 'Jessica Nakamura', slug: 'jessica', personaId: 'jessica',
  action: 'give_store_credit',
  parameters: { customer_id: 'CUST-JESSICA', amount_cents: 10000, reason: 'Store credit for 2 returned items: Waffle Bath Robe, Sage (order 301); Reed Diffuser (order 302).' },
  amountCents: 10000, amount: '100.00', reason: 'Store credit for 2 returned items: Waffle Bath Robe, Sage (order 301); Reed Diffuser (order 302).',
  sourceTurnId: 'turn-investigation-1', orderId: 301, orderIds: [301, 302], issue: 'Two items went back, no credit recorded.',
  recommendation: { primaryAction: 'give_store_credit', rationale: 'Two items went back, no credit recorded.', orderIds: [301, 302], items: ['Waffle Bath Robe, Sage', 'Reed Diffuser'] },
  actionHash: ACTION_HASH, requestedBySub: 'sub-nadia', requesterKind: 'operator', requestedAt: '2026-10-04T15:00:00Z',
}

export const PENDING_REVIEW = {
  ...BASE_REVIEW, status: 'pending', humanState: 'confirmation_required',
  assurance: { human: 'CONFIRMATION_REQUIRED', policy: 'PENDING', aurora: 'NOT_EVALUATED', evidence: 'PENDING' },
  executionTurnId: null, execution: null, decidedBy: null, decidedByName: null, decidedAt: null,
}

export const APPROVED_REVIEW = {
  ...PENDING_REVIEW, status: 'approved', humanState: 'confirmed', decidedBy: 'sub-nadia', decidedByName: 'nadia',
  decidedAt: '2026-10-04T15:02:00Z',
  assurance: { human: 'CONFIRMED', policy: 'PENDING', aurora: 'NOT_EVALUATED', evidence: 'PENDING' },
}

export const EXECUTED_REVIEW = {
  ...APPROVED_REVIEW, executionTurnId: 'turn-execution-1',
  assurance: { human: 'CONFIRMED', policy: 'ALLOW', aurora: 'PERMITTED', evidence: 'RECEIPTED' },
  execution: {
    receiptId: 9, executionTurnId: 'turn-execution-1', tool: 'give_store_credit',
    gatewayActionId: 'pellier-store-tools___give_store_credit', rail: 'gateway-mcp',
    actorPrincipal: 'sub-nadia', customerSubject: 'sub-jessica', policyEngineId: 'pellier_policy_engine-abc',
    gatewayMode: 'ENFORCE', matchingForbids: ['workshop_credit_limit'], idempotencyKey: WRITE_KEY,
    notes: { policy: 'AgentCore Policy evaluated the action and permitted it.', aurora: 'The runtime role was in scope and the transaction committed.' },
    recordedAt: '2026-10-04T15:03:00Z',
  },
}

export const RECORDED_ONCE = { idempotencyKey: WRITE_KEY, creditRows: 1, creditIds: [12], amountCents: 10000, auditRows: 1, auditIds: [4051], readable: true }

export function detail(review: Record<string, unknown>, record: Record<string, unknown> | null = null) {
  return {
    review,
    client: { customerId: 'CUST-JESSICA', name: 'Jessica Nakamura', slug: 'jessica', personaId: 'jessica' },
    orders: ORDERS.slice(0, 2),
    record,
  }
}

export const EXECUTE_RESULT = {
  reviewId: 41, rail: 'gateway-mcp', executionTurnId: 'turn-execution-1', idempotencyKey: WRITE_KEY,
  actorPrincipal: 'sub-nadia', customerSubject: 'sub-jessica', assurance: EXECUTED_REVIEW.assurance,
  notes: EXECUTED_REVIEW.execution.notes, tool: 'give_store_credit',
  result: { status: 'success', credit_id: 12, amount: '100.00', idempotent_replay: false }, record: RECORDED_ONCE,
}

const step = (id: string, label: string, status: string, extra: Record<string, unknown> = {}) => ({
  type: 'step', id, label, status, tags: id === 'planner' ? ['Planner', 'Approval'] : id === 'investigator' ? ['Investigator'] : ['Aurora'],
  builder: { tool: id.startsWith('get_') ? id : null, rail: 'in-process', agent: id === 'planner' ? 'planner' : 'investigator' },
  ...extra,
})

export const INVESTIGATION_EVENTS: Array<[string, unknown]> = [
  ['status', { type: 'status', turnId: 'turn-investigation-1', label: 'Investigator reads the case' }],
  ['step', step('investigator', 'Investigator reads the case', 'running')],
  ['step', step('get_tickets', "Reading Jessica's tickets", 'running')],
  ['step', step('get_tickets', "Reading Jessica's tickets", 'done', { finding: '1 open ticket: Two items went back, no credit yet', builder: { tool: 'get_tickets', rail: 'in-process', duration_ms: 42, audit_id: 4048, agent: 'investigator' } })],
  ['step', step('get_orders', "Reading Jessica's orders", 'running')],
  ['step', step('get_orders', "Reading Jessica's orders", 'done', { finding: '5 orders on file, $395.00 paid', builder: { tool: 'get_orders', rail: 'in-process', duration_ms: 38, audit_id: 4049, agent: 'investigator' } })],
  ['step', step('get_return_policy', 'Reading the return policy', 'running')],
  ['step', step('get_return_policy', 'Reading the return policy', 'done', { finding: '30-day returns for Home', builder: { tool: 'get_return_policy', rail: 'in-process', duration_ms: 21, audit_id: 4050, agent: 'investigator' } })],
  ['step', step('investigator', 'Investigator reads the case', 'done', { finding: '3 things the records show, 1 missing', builder: { tool: null, rail: 'in-process', duration_ms: 4200, agent: 'investigator' } })],
  ['step', step('planner', 'Planner proposes a credit', 'running')],
]

export const ANSWER = {
  type: 'answer', turnId: 'turn-investigation-1', customerId: 'CUST-JESSICA', status: 'complete',
  investigation: {
    facts: [
      'Jessica ordered the Waffle Bath Robe, Sage for $64.00 and the Reed Diffuser for $36.00 on the same day.',
      'Her open ticket says both items went back and were received.',
      'Home items can be returned within 30 days for a refund to the original payment.',
    ],
    missing: ['No store credit is recorded for the two returned items.'],
  },
  planner: 'A $100.00 store credit is proposed for the robe and the diffuser; a person must approve it before anything is written.',
  proposal: { reviewId: 41, customerId: 'CUST-JESSICA', amountCents: 10000, amount: '100.00', reason: 'Store credit for 2 returned items: Waffle Bath Robe, Sage (order 301); Reed Diffuser (order 302).', orderIds: [301, 302], actionHash: ACTION_HASH, idempotencyKey: WRITE_KEY, status: 'pending' },
  graph: { graphId: 'operator-investigation-v2', pattern: 'strands-graph', execution: 'in-process', modelId: 'global.anthropic.claude-sonnet-5', nodes: [{ nodeId: 'investigator', status: 'completed', durationMs: 4200 }, { nodeId: 'planner', status: 'completed', durationMs: 2900 }], durationMs: 7100 },
  error: null,
}

export const INVESTIGATION_TAIL: Array<[string, unknown]> = [
  ['step', step('planner', 'Planner proposes a credit', 'done', { finding: '$100.00 credit proposed for 2 returned items, waiting for approval', builder: { tool: null, rail: 'in-process', duration_ms: 2900, agent: 'planner' } })],
  ['answer', ANSWER],
  ['complete', { ...ANSWER, type: 'complete' }],
]

export function sse(events: Array<[string, unknown]>): string {
  return events.map(([kind, data]) => `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`).join('')
}
