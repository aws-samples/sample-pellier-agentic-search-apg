import { expect, test, type Page } from '@playwright/test'

// Deterministic fixtures for a Concierge turn whose stream is cut off. UI proof,
// not live execution evidence: the server's side is scripted, and the backend
// suites prove that the turn keeps running and is settled.
const client = {
  customerId: 'CUST-JESSICA', slug: 'jessica', name: 'Jessica Nakamura', personaId: null,
  membership: 'circle', spend12mo: 3940, orderCount: 1, orderValue: 325.36,
  note: 'A return request for the Coral Lacquer Catchall.', openCase: 'Return request',
  openCaseStatus: 'pending', openTicketCount: 1, creditBalanceCents: 0,
}
const SESSION = 'opc-cust-jessica-recovery'
const REQUEST_TEXT = 'Summarize this client for a service call.'
const request = {
  messageId: 1, role: 'user', content: REQUEST_TEXT, turnId: 'turn-cut-off',
  turnState: 'incomplete', actorType: 'operator', artifact: null, artifactVersion: 2, createdAt: null,
}
const SETTLED = 'This request stopped before an answer was saved. ' +
  'No review was prepared and nothing changed for this client. You can send it again.'
const interrupted = {
  messageId: 2, role: 'assistant', content: SETTLED, turnId: 'turn-cut-off',
  turnState: 'interrupted', actorType: 'assistant', artifactVersion: 2, createdAt: null,
  artifact: { primaryLabel: 'Request interrupted', proposedActions: [], sections: [] },
}

type ServerTurn = 'none' | 'running' | 'settled'

async function wire(page: Page) {
  const server = { turn: 'none' as ServerTurn, created: 0, streams: 0 }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/auth/me') return route.fulfill({ json: { userId: 'ui-operator', email: 'ui-fixture@example.invalid', givenName: 'UI fixture' } })
    if (path === '/api/user/preferences') return route.fulfill({ json: { preferences: null } })
    if (path === '/api/operator/clients') return route.fulfill({ json: { clients: [client], total: 1, byMembership: { circle: 1, maison: 0, registered: 0 } } })
    if (path === `/api/operator/clients/${client.customerId}`) return route.fulfill({ json: {
      client, orders: [], returns: [], credits: [], tickets: [], dataSource: 'UI recovery fixture',
    } })
    if (path === '/api/operator/concierge/config') return route.fulfill({ json: {
      composerEnabled: true, orchestrationAvailable: true, supportedWorkflowKinds: ['client_summary'],
      note: 'UI recovery fixture. No live actions.',
    } })
    if (path === '/api/operator/capabilities') return route.fulfill({ json: {
      capabilities: { client_read: { state: 'available' } }, governedActionsAvailable: false, ttlSeconds: 60,
    } })
    if (path === '/api/operator/reviews') return route.fulfill({ json: { reviews: [], total: 0, pendingCount: 0 } })
    if (path.endsWith('/concierge/sessions/latest')) {
      return route.fulfill({ json: { sessionId: server.turn === 'none' ? null : SESSION } })
    }
    if (path.endsWith('/concierge/sessions') && method === 'POST') {
      server.created += 1
      return route.fulfill({ json: { sessionId: SESSION, customerId: client.customerId, messages: [] } })
    }
    if (path.endsWith('/turns/stream') && method === 'POST') {
      // The request is saved and reported, then the connection drops mid-turn.
      server.streams += 1
      server.turn = 'running'
      return route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: 'event: step\ndata: {"kind":"request","label":"Request saved","source":"Local PostgreSQL","status":"complete"}\n\n',
      })
    }
    if (path.endsWith(`/concierge/sessions/${SESSION}`)) {
      return route.fulfill({ json: {
        sessionId: SESSION, customerId: client.customerId, truncated: false,
        messages: server.turn === 'settled' ? [request, interrupted] : [request],
        openTurn: server.turn === 'running' ? { turnId: 'turn-cut-off', messageId: 1, state: 'running' } : null,
      } })
    }
    if (path.startsWith('/api/operator/') && method !== 'GET') {
      return route.fulfill({ status: 405, json: { error: 'The recovery fixture allows no other mutation' } })
    }
    return route.continue()
  })
  return server
}

test.use({ contextOptions: { reducedMotion: 'reduce' }, trace: 'off' })
test('a cut-off turn keeps working through a reload, then settles into a usable conversation', async ({ page }) => {
  const server = await wire(page)
  await page.goto('/operator/clients/CUST-JESSICA#operator-concierge')
  const concierge = page.getByTestId('operator-concierge')
  const composer = concierge.getByRole('textbox')

  await composer.fill(REQUEST_TEXT)
  await composer.press('Enter')

  // The stream ended early, and the saved request is shown as still being answered.
  const state = concierge.getByTestId('operator-concierge-turnstate')
  await expect(state).toHaveAttribute('data-turn-state', 'running')
  await expect(state).toContainText('Working')
  await expect(concierge.getByTestId('operator-concierge-working')).toBeVisible()
  await expect(composer).toHaveAttribute('readonly', '')
  await expect(composer).toHaveValue('')

  // A reload reattaches to the same turn: no error, no new conversation.
  await page.reload()
  await expect(concierge.getByTestId('operator-concierge-turnstate')).toHaveAttribute('data-turn-state', 'running')
  await expect(concierge.getByText(REQUEST_TEXT)).toBeVisible()
  await expect(concierge.getByRole('button', { name: 'Retry history' })).toHaveCount(0)

  // The server settles the turn; the waiting page shows it without another reload.
  server.turn = 'settled'
  await expect(concierge.getByTestId('operator-concierge-primary-label')).toHaveText('Request interrupted', { timeout: 10_000 })
  await expect(concierge.getByText(SETTLED)).toBeVisible()
  await expect(concierge.getByText(REQUEST_TEXT)).toBeVisible()
  await expect(concierge.getByTestId('operator-concierge-working')).toHaveCount(0)
  await expect(composer).not.toHaveAttribute('readonly', '')
  await expect(concierge.getByRole('button', { name: 'Retry this request' })).toBeEnabled()

  expect(server.created).toBe(1)
  expect(server.streams).toBe(1)
})
