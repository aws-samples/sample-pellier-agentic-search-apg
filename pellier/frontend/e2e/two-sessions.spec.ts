/**
 * Lab 4 in one browser: Nadia on the Operator, Jessica on the storefront.
 *
 * Against the real app with every `/api` call answered by a stand-in that
 * keeps the backend's cookie contract: the shopper session lives in
 * `access_token`, the staff session in `staff_access_token`, the storefront
 * and `?surface=shopper` read only the first, and the Operator and
 * `?surface=staff` read only the second. Sign-ins write real httpOnly cookies
 * into the one browser context both tabs share. No Cognito and no model. Run
 * against the Vite dev server:
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/two-sessions.spec.ts
 */
import { expect, test, type BrowserContext, type Route } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { BOOK, OPEN_REQUEST } from './fixtures/jessica-case'

const SHOPPERS = ['marco', 'anna', 'theo', 'jessica']
const NAMES: Record<string, string> = { marco: 'Marco', anna: 'Anna', theo: 'Theo', jessica: 'Jessica' }
const COOKIE = { shopper: 'access_token', staff: 'staff_access_token' } as const
type Surface = keyof typeof COOKIE

function profile(id: string) {
  return {
    id, edit: id === 'jessica' ? 'house' : id, display_name: NAMES[id], role_tag: `${NAMES[id]}'s edit`,
    blurb: 'Live profile.', avatar_color: '#5a4535', avatar_initial: NAMES[id][0],
    customer_id: id === 'fresh' || id === 'nadia' ? null : `CUST-${id.toUpperCase()}`,
    hero_image: '/products/hero-theo.png', hero_alt: NAMES[id], hero_subheadline: 'Live profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  }
}

/** What the stand-in recorded: every request's surface, and Jessica's credit ask. */
interface Desk {
  requests: Array<typeof OPEN_REQUEST>
  staffReads: string[]
  /** Sessions issued by /api/persona/switch, and the one each chat turn carried. */
  sessions: number
  chatSessions: string[]
  historyReads: string[]
  failSwitch: boolean
  /** What the Router step says Memory gave Theo's next turn: ids, a failed read, or none read. */
  remembered: string[] | 'failed' | null
}

async function serve(context: BrowserContext, baseURL: string): Promise<Desk> {
  const desk: Desk = {
    requests: [], staffReads: [], sessions: 0, chatSessions: [], historyReads: [], failSwitch: false, remembered: null,
  }
  const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const session = async (route: Route, surface: Surface): Promise<string | null> => {
    const header = (await route.request().headerValue('cookie')) ?? ''
    const pair = header.split(/;\s*/).find(item => item.startsWith(`${COOKIE[surface]}=`))
    return pair ? decodeURIComponent(pair.slice(COOKIE[surface].length + 1)) : null
  }
  const signIn = (surface: Surface, username: string) => context.addCookies([{
    name: COOKIE[surface], value: username, url: baseURL, httpOnly: true, sameSite: 'Lax',
  }])

  await context.route('**/assets/personas/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.alloc(0) }))
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace(/^\/ports\/\d+/, '')
    const method = route.request().method()
    const body = method === 'POST' ? route.request().postDataJSON() ?? {} : {}
    const surface: Surface = url.searchParams.get('surface') === 'staff' ? 'staff' : 'shopper'

    if (path.endsWith('/api/auth/password/csrf')) return route.fulfill(json({ csrfToken: 'csrf' }))
    if (path.endsWith('/api/auth/password/workshop-sign-in')) {
      if (!SHOPPERS.includes(body.username)) return route.fulfill(json({ detail: 'workshop_user_not_allowed' }, 403))
      await signIn('shopper', body.username)
      return route.fulfill(json({ status: 'signed_in', returnTo: '/', username: body.username, signInMethod: 'workshop' }))
    }
    if (path.endsWith('/api/auth/password/sign-in')) {
      const target: Surface = body.surface === 'staff' ? 'staff' : 'shopper'
      if (target === 'shopper' && body.username === 'nadia') return route.fulfill(json({ detail: 'staff_use_operator' }, 403))
      await signIn(target, body.username)
      return route.fulfill(json({ status: 'signed_in', returnTo: body.returnTo ?? '/' }))
    }
    if (path.endsWith('/api/auth/me')) {
      const username = await session(route, surface)
      if (surface === 'staff') desk.staffReads.push(username ?? 'none')
      return username
        ? route.fulfill(json({ user_id: `sub-${username}`, email: `${username}@pellier.example.com`, username, sign_in_method: surface === 'shopper' ? 'workshop' : 'cognito' }))
        : route.fulfill(json({ error: 'auth_failed' }, 401))
    }
    if (path.includes('/api/auth/')) return route.fulfill(json({ error: 'refresh_failed' }, 401))
    if (path.endsWith('/api/user/preferences')) {
      return (await session(route, 'shopper')) ? route.fulfill(json({ preferences: null })) : route.fulfill(json({ error: 'auth_failed' }, 401))
    }
    if (path.endsWith('/api/personas')) return route.fulfill(json(SHOPPERS.map(profile)))
    if (path.endsWith('/api/persona/switch')) {
      if (desk.failSwitch) return route.fulfill(json({ detail: 'unavailable' }, 503))
      desk.sessions += 1
      const sessionId = `persona-${body.persona_id}-${desk.sessions.toString(16).padStart(32, '0')}`
      return route.fulfill(json({ session_id: sessionId, persona: profile(body.persona_id) }))
    }
    if (path.includes('/api/agent/session/')) {
      desk.historyReads.push(decodeURIComponent(path.split('/api/agent/session/')[1]))
      return route.fulfill(json({ turns: [] }))
    }
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: null }))
    if (path.endsWith('/api/chat/stream')) {
      // The storefront turn runs as the shopper session, never the staff one.
      const shopper = await session(route, 'shopper')
      if (shopper === 'jessica' && /credit/i.test(String(body.message ?? ''))) desk.requests.push(OPEN_REQUEST)
      const principal = shopper
        ? { authenticated: true, customerId: `CUST-${shopper.toUpperCase()}`, signInMethod: 'workshop' }
        : { authenticated: false, customerId: null, signInMethod: null }
      desk.chatSessions.push(String(body.session_id ?? ''))
      const turn = `turn-${desk.chatSessions.length.toString(16).padStart(32, 'c')}`
      const reply = 'I passed your request to a person on the team.'
      const memory = { source: 'agentcore-memory', strategy: 'USER_PREFERENCE' }
      const remembered = shopper !== 'theo' || desk.remembered === null ? null
        : desk.remembered === 'failed' ? { ...memory, records: [], error: 'memory_read_failed' }
          : { ...memory, records: desk.remembered }
      const events = [
        { type: 'turn_start', turn_id: turn, session_id: body.session_id, principal },
        {
          type: 'step', id: 'route', label: 'Understanding your request', status: 'done', tags: ['Router', 'Memory'],
          builder: { tool: null, intent: 'catalog', agent: 'Catalog agent', remembered },
        },
        { type: 'content', content: reply },
        { type: 'complete', response: { response: reply, products: [], suggestions: [], turn_id: turn } },
      ]
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('') })
    }
    if (path.includes('/api/operator/')) {
      // The desk reads the staff session only.
      const staff = await session(route, 'staff')
      if (!staff) return route.fulfill(json({ detail: 'authentication_required' }, 401))
      if (staff !== 'nadia') return route.fulfill(json({ detail: 'operator_group_required' }, 403))
      if (path.endsWith('/api/operator/clients')) return route.fulfill(json(BOOK))
      if (path.endsWith('/api/operator/reviews')) {
        return route.fulfill(json({ reviews: [], requests: desk.requests, total: 0, pendingCount: 0, openRequestCount: desk.requests.length }))
      }
    }
    if (path.endsWith('/api/products')) return route.fulfill(json([]))
    if (path.endsWith('/api/scenarios')) return route.fulfill(json({ scenarios: [] }))
    return route.fulfill(json({}))
  })
  return desk
}

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.setItem('pellier-builder-view', 'on')
  })
})

test('Nadia stays signed in on the Operator while Jessica asks for her credit in another tab', async ({ context, baseURL }) => {
  const desk = await serve(context, baseURL ?? 'http://localhost:8000')

  // Tab one: Nadia signs in on the Operator with her password.
  const operator = await context.newPage()
  await operator.setViewportSize({ width: 1440, height: 900 })
  await operator.goto('/operator')
  await operator.getByTestId('operator-sign-in').click()
  await expect(operator).toHaveURL(/\/signin\?returnTo=%2Foperator/)
  await operator.getByLabel('Username', { exact: true }).fill('nadia')
  await operator.getByLabel('Password', { exact: true }).fill('typed')
  await operator.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(operator.getByTestId('operator-staff')).toContainText('Nadia')
  await operator.getByTestId('operator-reviews-link').click()
  await expect(operator.getByTestId('operator-reviews-empty')).toBeVisible()
  await expect(operator.getByTestId('operator-requests')).toHaveCount(0)

  // Tab two: the storefront, where Jessica's card in the docked panel is the
  // one click.
  const store = await context.newPage()
  await store.setViewportSize({ width: 1440, height: 900 })
  await store.goto('/')
  await store.getByTestId('ask-shopper-jessica').click()
  await expect(store.getByTestId('ask-signed-in-name')).toHaveText('Jessica')
  await expect(store.getByTestId('ask-signed-in-name')).toHaveText('Jessica')

  // She asks for her credit; the turn runs as Jessica.
  const ask = store.getByTestId('pellier-hero-search')
  await ask.fill('I sent the robe and the diffuser back. Can I have a store credit?')
  await ask.press('Enter')
  const drawer = store.getByTestId('chat-drawer')
  await expect(drawer.getByTestId('turn-principal').last()).toContainText('Workshop sign-in, CUST-JESSICA')
  expect(desk.requests).toHaveLength(1)

  // Both sessions sit side by side in the one browser.
  const cookies = await context.cookies()
  expect(cookies.find(cookie => cookie.name === 'access_token')?.value).toBe('jessica')
  expect(cookies.find(cookie => cookie.name === 'staff_access_token')?.value).toBe('nadia')

  // Back on the Operator: Nadia is still signed in and sees Jessica's request.
  await operator.bringToFront()
  await operator.reload()
  await expect(operator.getByTestId('operator-staff')).toContainText('Nadia')
  const request = operator.getByTestId(`operator-request-${OPEN_REQUEST.requestId}`)
  await expect(request).toContainText('Jessica Nakamura')
  await expect(request).toContainText('Open request')
  expect(desk.staffReads.at(-1)).toBe('nadia')
  expect(desk.staffReads).not.toContain('jessica')
})

const THEO_SHOTS = process.env.THEO_SHOTS ?? 'test-results/theo-states'

for (const [width, theme] of [[1440, 'light'], [390, 'dark']] as const) {
  test(`Theo starts a new conversation and keeps his sign-in, ${theme} theme at ${width}px`, async ({ context, baseURL }) => {
    const desk = await serve(context, baseURL ?? 'http://localhost:8000')
    const store = await context.newPage()
    await store.emulateMedia({ colorScheme: theme })
    await store.setViewportSize({ width, height: width < 760 ? 844 : 900 })
    mkdirSync(THEO_SHOTS, { recursive: true })
    const drawer = store.getByTestId('chat-drawer')
    const shot = (name: string) => drawer.screenshot({ path: join(THEO_SHOTS, `${name}-${theme}-${width}.png`) })
    await store.goto('/')
    if (!(await drawer.isVisible())) await store.getByTestId('header-ask-pellier').click()
    await drawer.getByTestId('ask-shopper-theo').click()
    await expect(drawer.getByTestId('ask-signed-in-name')).toHaveText('Theo')
    const composer = drawer.getByRole('textbox', { name: 'Message Pellier' })
    const said = "I'm drawn to deep indigo linen."

    desk.remembered = []
    await composer.fill(said)
    await composer.press('Enter')
    await expect(drawer.getByTestId('turn-principal').last()).toContainText('CUST-THEO')
    await expect(drawer.getByText(said)).toBeVisible()

    // A failed request leaves the conversation as it was, still usable.
    desk.failSwitch = true
    await drawer.getByRole('button', { name: 'New conversation' }).click()
    await expect(drawer.getByTestId('ask-new-conversation-failed'))
      .toHaveText("Pellier couldn't start a new conversation. This one is still open.")
    await expect(drawer.getByText(said)).toBeVisible()
    await expect(composer).toBeEnabled()
    desk.failSwitch = false

    await drawer.getByRole('button', { name: 'New conversation' }).click()
    await expect(drawer.getByTestId('ask-new-conversation-note')).toHaveText('New conversation. You are still signed in as Theo.')
    await expect(drawer.getByText(said)).toHaveCount(0)
    await expect(drawer.getByTestId('ask-new-conversation-failed')).toHaveCount(0)
    await expect(drawer.getByTestId('ask-signed-in-name')).toHaveText('Theo')
    await expect(composer).toBeFocused()
    expect((await context.cookies()).find(cookie => cookie.name === 'access_token')?.value).toBe('theo')
    await shot('1-new-conversation')

    desk.remembered = ['mem-theo-indigo']
    await composer.fill('What would you recommend for my home?')
    await composer.press('Enter')
    await expect(drawer.getByTestId('turn-principal').last()).toContainText('CUST-THEO')
    const [first, second] = desk.chatSessions
    expect(desk.chatSessions).toHaveLength(2)
    expect(first).toMatch(/^persona-theo-[0-9a-f]{32}$/)
    expect(second).toMatch(/^persona-theo-[0-9a-f]{32}$/)
    expect(second).not.toBe(first)
    // The new conversation asked for its own history, and none of the old turns show.
    expect(desk.historyReads).toContain(second)
    await expect(drawer.getByText(said)).toHaveCount(0)

    // Builder view, Understanding your request, Memory: the count, then the id folded under it.
    const fold = drawer.getByTestId('turn-fold').last()
    if ((await fold.getAttribute('aria-expanded')) === 'false') await fold.click()
    await expect(drawer.getByText('The agent received one saved preference.')).toBeVisible()
    const records = drawer.getByTestId('turn-memory-records').last()
    await expect(records).not.toHaveAttribute('open', '')
    await records.locator('summary').click()
    await expect(records).toContainText('mem-theo-indigo')
    await records.scrollIntoViewIfNeeded()
    await shot('2-memory-record')

    // An empty read and a failed read each say what they are.
    for (const [remembered, words] of [
      [[], 'AgentCore Memory held no saved preference, so the agent received none.'],
      ['failed', 'The AgentCore Memory read failed (memory_read_failed), so the agent received no saved preference.'],
    ] as const) {
      desk.remembered = remembered === 'failed' ? 'failed' : []
      await composer.fill('Anything else for the table?')
      await composer.press('Enter')
      const latest = drawer.getByTestId('turn-fold').last()
      await expect(latest).toBeVisible()
      if ((await latest.getAttribute('aria-expanded')) === 'false') await latest.click()
      await expect(drawer.getByText(words)).toBeVisible()
    }

    const overflow = await store.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(0)

    // Choosing Marco is still a shopper switch, with its own session.
    await drawer.getByTestId('ask-switch-shopper').click()
    await drawer.getByTestId('ask-shopper-marco').click()
    await expect(drawer.getByTestId('ask-signed-in-name')).toHaveText('Marco')
    await expect(drawer.getByRole('button', { name: 'New conversation' })).toHaveCount(0)
  })
}
