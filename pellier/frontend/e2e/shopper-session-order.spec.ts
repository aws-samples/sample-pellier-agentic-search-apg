/**
 * A slow "Sign in again" never leaves the Storefront on one shopper and the session on another.
 *
 * Against the real app with every `/api` call answered by a stand-in that keeps the shopper
 * session in a real cookie. The workshop sign-in sets it with `Set-Cookie`, and a response the
 * page has already abandoned never reaches the browser, so the cookie jar behaves as it does
 * on an event. `/api/auth/me` and the chat stream read the cookie the browser sent. Run
 * against the Vite dev server:
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/shopper-session-order.spec.ts
 */
import { expect, test, type Page, type Route } from '@playwright/test'

const SHOPPERS = ['marco', 'anna', 'theo', 'jessica'] as const
const NAMES: Record<string, string> = { marco: 'Marco', anna: 'Anna', theo: 'Theo', jessica: 'Jessica', nadia: 'Nadia', fresh: 'Pellier guest' }
const COOKIE = 'pellier_shopper'
const FAILED_QUESTION = 'Where is my ticket?'

function profile(id: string) {
  return {
    id, edit: id === 'jessica' ? 'house' : id, display_name: NAMES[id], role_tag: `${NAMES[id]}'s edit`,
    blurb: 'Live profile.', avatar_color: '#5a4535', avatar_initial: NAMES[id][0],
    customer_id: id === 'fresh' || id === 'nadia' ? null : `CUST-${id.toUpperCase()}`,
    hero_image: '/products/hero-theo.png', hero_alt: NAMES[id], hero_subheadline: 'Live profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  }
}

interface Server {
  /** The next chat turn answers 401, as it does once the shopper's token has expired. */
  expired: boolean
  /** Chat turns the stand-in received. */
  turns: number
  /** Holds Theo's next workshop sign-in until the test lets his response go. */
  holdTheo: Promise<void> | null
  /** Called when Theo's held sign-in reaches the server. */
  theoHeld: () => void
  /** The next workshop sign-in is refused. */
  refuseNext: boolean
}

async function shopperCookie(route: Route): Promise<string | null> {
  const header = (await route.request().allHeaders()).cookie ?? ''
  const match = header.split(/;\s*/).find(part => part.startsWith(`${COOKIE}=`))
  return match ? match.slice(COOKIE.length + 1) : null
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return { status, contentType: 'application/json', headers, body: JSON.stringify(body) }
}

async function fulfillIfStillOpen(route: Route, response: ReturnType<typeof json>) {
  // A request the page abandoned has no one left to answer.
  await route.fulfill(response).catch(() => {})
}

async function workshopSignIn(route: Route, server: Server) {
  const { username } = route.request().postDataJSON() as { username: string }
  if (server.refuseNext) {
    server.refuseNext = false
    return fulfillIfStillOpen(route, json({ detail: 'workshop_sign_in_unavailable' }, 503))
  }
  if (username === 'theo' && server.holdTheo) {
    server.theoHeld()
    await server.holdTheo
  }
  server.expired = false
  await fulfillIfStillOpen(route, json(
    { status: 'signed_in', username, signInMethod: 'workshop' },
    200,
    { 'set-cookie': `${COOKIE}=${username}; Path=/; SameSite=Lax` },
  ))
}

function chatStream(shopper: string | null) {
  const principal = shopper
    ? { authenticated: true, customerId: `CUST-${shopper.toUpperCase()}`, signInMethod: 'workshop' }
    : { authenticated: false, customerId: null, signInMethod: null }
  const events = [
    { type: 'turn_start', turn_id: 'turn-' + 'c'.repeat(32), session_id: 's', principal },
    { type: 'content', content: 'Here is what I found.' },
    { type: 'complete', response: { response: 'Here is what I found.', products: [], suggestions: [], turn_id: 'turn-' + 'c'.repeat(32) } },
  ]
  return { status: 200, contentType: 'text/event-stream', body: events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('') }
}

async function serve(page: Page): Promise<Server> {
  const server: Server = {
    expired: false,
    turns: 0,
    holdTheo: null,
    theoHeld: () => {},
    refuseNext: false,
  }
  await page.route('**/assets/personas/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.alloc(0) }))
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/ports\/\d+/, '')
    const body = route.request().method() === 'POST' ? route.request().postDataJSON() ?? {} : {}
    const shopper = await shopperCookie(route)
    if (path.endsWith('/api/auth/password/csrf')) return route.fulfill(json({ csrfToken: 'csrf' }))
    if (path.endsWith('/api/auth/password/workshop-sign-in')) return workshopSignIn(route, server)
    if (path.endsWith('/api/auth/me')) {
      return shopper
        ? route.fulfill(json({ user_id: `sub-${shopper}`, email: `${shopper}@pellier.example.com`, username: shopper, sign_in_method: 'workshop' }))
        : route.fulfill(json({ error: 'auth_failed' }, 401))
    }
    if (path.includes('/api/auth/')) return route.fulfill(json({ error: 'refresh_failed' }, 401))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    if (path.endsWith('/api/personas')) return route.fulfill(json(['fresh', 'nadia', ...SHOPPERS].map(profile)))
    if (path.endsWith('/api/persona/switch')) {
      return route.fulfill(json({ session_id: `persona-${body.persona_id}-${'0'.repeat(32)}`, persona: profile(body.persona_id) }))
    }
    if (path.endsWith('/api/persona/current')) return route.fulfill(json({ persona: null }))
    if (path.endsWith('/api/chat/stream')) {
      server.turns += 1
      if (server.expired) return route.fulfill(json({ error: 'auth_failed' }, 401))
      return route.fulfill(chatStream(shopper))
    }
    if (path.endsWith('/api/products')) return route.fulfill(json([]))
    if (path.endsWith('/api/scenarios')) return route.fulfill(json({ scenarios: [] }))
    return route.fulfill(json({}))
  })
  return server
}

/** Who the server says the browser's session cookie belongs to. */
async function meSays(page: Page): Promise<string | null> {
  return page.evaluate(async () => {
    const response = await fetch('/api/auth/me?surface=shopper')
    return response.ok ? ((await response.json()) as { username: string }).username : null
  })
}

/** Choose Theo, let his token expire, and ask until the card offers Sign in again. */
async function expireTheosSession(page: Page, server: Server) {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByTestId('ask-shopper-theo').click()
  await expect(page.getByTestId('ask-signed-in-name')).toHaveText('Theo')
  server.expired = true
  const drawer = page.getByTestId('chat-drawer')
  const composer = drawer.getByRole('textbox', { name: 'Message Pellier' })
  await composer.fill(FAILED_QUESTION)
  await composer.press('Enter')
  await expect(drawer.getByRole('button', { name: 'Sign in again' })).toBeVisible()
  expect(server.turns).toBe(1)
  return drawer
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.setItem('pellier-builder-view', 'on')
  })
})

test('Theo’s slow sign in again cannot take the session from Anna, who was chosen after it', async ({ page, context }) => {
  const server = await serve(page)
  const drawer = await expireTheosSession(page, server)
  let release = () => {}
  server.holdTheo = new Promise<void>(resolve => { release = resolve })
  const reachedServer = new Promise<void>(resolve => { server.theoHeld = resolve })

  await drawer.getByRole('button', { name: 'Sign in again' }).click()
  await reachedServer

  await page.getByTestId('ask-switch-shopper').click()
  await page.getByTestId('ask-shopper-anna').click()
  await expect(page.getByTestId('ask-signed-in-name')).toHaveText('Anna')

  // Theo's response is released after Anna is signed in.
  release()
  await page.waitForTimeout(300)
  await expect(page.getByTestId('ask-signed-in-name')).toHaveText('Anna')
  expect(await meSays(page)).toBe('anna')
  expect((await context.cookies()).find(cookie => cookie.name === COOKIE)?.value).toBe('anna')
  // Nothing was sent again for Theo.
  expect(server.turns).toBe(1)
})

test('sign in again signs the same shopper in once and sends the request once', async ({ page }) => {
  const server = await serve(page)
  const drawer = await expireTheosSession(page, server)

  await drawer.getByRole('button', { name: 'Sign in again' }).click()
  await expect(drawer.getByText(FAILED_QUESTION, { exact: true }).first()).toBeVisible()
  await expect(drawer.getByTestId('turn-principal').last()).toHaveText('IdentityWorkshop sign-in, CUST-THEO')
  await expect(drawer.getByTestId('ask-signed-in-name')).toHaveText('Theo')
  expect(await meSays(page)).toBe('theo')
  expect(server.turns).toBe(2)
})

test('a sign in again that fails says so, and trying again sends the request', async ({ page }) => {
  const server = await serve(page)
  const drawer = await expireTheosSession(page, server)

  server.refuseNext = true
  await drawer.getByRole('button', { name: 'Sign in again' }).click()
  await expect(drawer.getByText('Pellier could not sign you in again. Try again in a moment.')).toBeVisible()
  expect(server.turns).toBe(1)

  await drawer.getByRole('button', { name: 'Sign in again' }).click()
  await expect(drawer.getByTestId('turn-principal').last()).toHaveText('IdentityWorkshop sign-in, CUST-THEO')
  expect(server.turns).toBe(2)
})
