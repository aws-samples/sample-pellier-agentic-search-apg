import { expect, test, type Page } from '@playwright/test'
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'

const require = createRequire(import.meta.url)

// Deterministic navigation fixtures. These are UI proof, not live execution
// evidence. Every Operator mutation is intercepted and fails this test.
const client = {
  customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura', personaId: null,
  membership: 'circle', spend12mo: 3940, orderCount: 1, orderValue: 325.36,
  note: 'A return request for the Coral Lacquer Catchall.', openCase: 'Return request',
  openCaseStatus: 'pending', openTicketCount: 1, creditBalanceCents: 0,
}
const order = {
  orderId: 406, productId: '41', productName: 'Coral Lacquer Catchall', brand: 'Pellier Maison',
  price: 325.36, quantity: 1, placedAt: null, imageUrl: '/products/house-coral-lacquer-catchall.png',
}
const review = {
  reviewId: 901, customerId: client.customerId, customerName: client.name, slug: client.slug,
  personaId: null, action: 'initiate_return', parameters: { customer_id: client.customerId, product_id: '41', reason: 'not_as_described' },
  status: 'pending', humanState: 'confirmation_required', sourceTurnId: 'proposal-turn',
  executionTurnId: null, execution: null, orderId: order.orderId, productName: order.productName,
  issue: 'Not as described', recommendation: { rationale: 'Review the exact item and reason.' },
  assurance: { human: 'CONFIRMATION_REQUIRED', policy: 'PENDING', aurora: 'NOT_EVALUATED', evidence: 'PENDING' },
  actionHash: 'ui-flow-fixture', requesterKind: 'staff', requestedAt: null, decidedAt: null,
}
const proposal = {
  tool: 'initiate_return', reviewId: 901, state: 'review_required',
  product: { name: order.productName, price: order.price }, order: { orderId: order.orderId },
  material: { reason: 'not_as_described' }, executionCapability: { state: 'review_required' },
}
const messages = [
  { messageId: 1, role: 'assistant', turnId: 'proposal-turn', turnState: 'complete',
    content: 'The return review is prepared. Read the exact terms before making a decision.',
    artifact: { proposedActions: [proposal], sections: Array.from({ length: 8 }, (_, i) => ({
      id: `source-${i}`, label: `Source record ${i + 1}`, tone: 'context',
      body: 'Fixture evidence for a long conversation. The order is recorded; a proposal is not an approval.',
    })) } },
  { messageId: 2, role: 'assistant', turnId: 'follow-up-turn', turnState: 'complete',
    content: 'The later discussion does not replace the prepared review.', artifact: null },
]

async function wire(page: Page, proposalInConversation = true) {
  const reads: string[] = []
  const mutations: string[] = []
  let latestSession = 'case-session'
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.startsWith('/api/operator/') && route.request().method() !== 'GET') {
      mutations.push(path)
      return route.fulfill({ status: 405, json: { error: 'UI navigation must not mutate' } })
    }
    if (path.startsWith('/api/operator/')) reads.push(path)
    if (path === '/api/auth/me') return route.fulfill({ json: { userId: 'ui-operator', email: 'ui-fixture@example.invalid', givenName: 'UI fixture' } })
    if (path === '/api/user/preferences') return route.fulfill({ json: { preferences: null } })
    if (path === '/api/operator/clients') return route.fulfill({ json: { clients: [client], total: 1, byMembership: { circle: 1, maison: 0, registered: 0 } } })
    if (path === `/api/operator/clients/${client.customerId}`) return route.fulfill({ json: {
      client, orders: [order], returns: [], credits: [], tickets: [], dataSource: 'UI flow fixture',
    } })
    if (path.endsWith('/concierge/sessions/latest')) return route.fulfill({ json: { sessionId: latestSession } })
    if (path.includes('/concierge/sessions/')) return route.fulfill({ json: {
      sessionId: path.split('/').at(-1), customerId: client.customerId,
      messages: path.endsWith('/case-session') ? proposalInConversation ? messages : [messages[1]] : [{ ...messages[1], content: 'A newer, unrelated conversation.' }],
    } })
    if (path === '/api/operator/concierge/config') return route.fulfill({ json: {
      composerEnabled: true, orchestrationAvailable: true, supportedWorkflowKinds: ['investigate_resolution'], note: 'UI flow fixture. No live actions.',
    } })
    if (path === '/api/operator/capabilities') return route.fulfill({ json: {
      capabilities: { client_read: { state: 'available' }, initiate_return: { state: 'review_required' } },
      governedActionsAvailable: false, ttlSeconds: 60,
    } })
    if (path === '/api/operator/reviews') return route.fulfill({ json: { reviews: [
      { ...review, reviewId: 900, customerId: 'CUST-THEO', customerName: 'Theo', slug: 'theo' }, review,
    ], total: 2, pendingCount: 2 } })
    if (path === '/api/operator/reviews/901') return route.fulfill({ json: {
      review, client, order, product: null, returns: [],
      fulfilment: { availabilityVerified: true, replacementAvailable: false, totalUnits: 0, warehouses: [] },
    } })
    return route.continue()
  })
  return { reads, mutations, startNewerConversation: () => { latestSession = 'newer-session' } }
}

async function accessible(page: Page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: typeof import('axe-core') }).axe
    return (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } }))
      .violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))
  })
  expect(violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false)
}

async function capture(page: Page, name: string) {
  const directory = process.env.PELLIER_OPERATOR_CAPTURE_DIR
  if (!directory) return
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: `${directory}/${name}.png` })
}

test.use({ reducedMotion: 'reduce', trace: 'off' })
test('a newer client conversation surfaces its own pending review from the queue', async ({ page }) => {
  const api = await wire(page, false)
  await page.setViewportSize({ width: 768, height: 960 })
  await page.goto('/operator/clients/CUST-JESSICA#operator-concierge')
  const handoff = page.getByRole('navigation', { name: 'Prepared reviews' })
  await expect(handoff).toContainText('A prepared action for Jessica Nakamura is awaiting human review.')
  await expect(handoff.getByRole('link')).toHaveCount(1)
  await expect(handoff.getByRole('link')).toHaveAttribute('href', '/operator/reviews/901?client=CUST-JESSICA&session=case-session&turn=follow-up-turn')
  await handoff.getByRole('link').click()
  await page.getByRole('link', { name: 'Return to conversation' }).click()
  await expect(page.locator('[data-turn-id="follow-up-turn"]')).toBeFocused()
  expect(api.mutations).toEqual([])
})

for (const width of [1440, 768, 390]) {
  test(`client chat, prepared review, and exact conversation return stay connected at ${width}px`, async ({ page }) => {
    const api = await wire(page)
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/operator')
    const row = page.getByTestId('operator-client-jessica')
    await expect(row).toContainText('Open chat')
    await row.focus()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/CUST-JESSICA#operator-concierge$/)
    await expect(page.getByTestId('operator-concierge-state')).not.toHaveAttribute('data-state', 'loading')
    const handoff = page.getByRole('navigation', { name: 'Prepared reviews' })
    await expect(handoff.getByRole('link', { name: 'Open review #901' })).toBeInViewport()
    await expect(page.getByTestId('operator-concierge-input')).toBeInViewport()
    // Scrolling the evidence cannot displace the next action or input.
    await page.getByTestId('operator-concierge-body').evaluate(node => { node.scrollTop = 0 })
    await expect(handoff.getByRole('link')).toBeInViewport()
    await capture(page, `fixture-chat-${width}`)
    await accessible(page)
    await handoff.getByRole('link').click()
    await expect(page.getByTestId('operator-review-confirm')).toBeVisible()
    await expect(page.getByTestId('operator-review-execute')).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Return to conversation' })).toBeVisible()
    await capture(page, `fixture-review-${width}`)
    await accessible(page)

    // Another conversation now exists. The return must still load the one
    // that supplied the handoff, even after the review itself is reloaded.
    api.startNewerConversation()
    await page.reload()
    const latestReads = api.reads.filter(path => path.endsWith('/sessions/latest')).length
    await page.getByRole('link', { name: 'Return to conversation' }).click()
    await expect(page).toHaveURL(/session=case-session&turn=proposal-turn#operator-concierge$/)
    const proposalTurn = page.locator('[data-turn-id="proposal-turn"]')
    await expect(proposalTurn).toBeFocused()
    await expect(page.getByTestId('operator-concierge-proposal')).toBeInViewport()
    expect(api.reads.filter(path => path.endsWith('/sessions/latest'))).toHaveLength(latestReads)
    expect(api.mutations).toEqual([])
    expect(errors).toEqual([])
  })
}
