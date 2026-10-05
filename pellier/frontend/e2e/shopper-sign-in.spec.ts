/**
 * Choosing a shopper signs in, and the next turn runs as them.
 *
 * Against the real app with every `/api` call answered by a small stand-in
 * server: the workshop sign-in sets the session, `/api/auth/me` reports it,
 * and the chat stream's `turn_start` names the principal the session holds,
 * the way `app.py` does. No Cognito and no model. Run against the Vite dev
 * server:
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/shopper-sign-in.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'

const SHOPPERS = ['marco', 'anna', 'theo', 'jessica'] as const
const NAMES: Record<string, string> = { marco: 'Marco', anna: 'Anna', theo: 'Theo', jessica: 'Jessica', nadia: 'Nadia', fresh: 'Pellier guest' }

function profile(id: string) {
  return {
    id, edit: id === 'jessica' ? 'house' : id, display_name: NAMES[id], role_tag: `${NAMES[id]}'s edit`,
    blurb: 'Live profile.', avatar_color: '#5a4535', avatar_initial: NAMES[id][0],
    customer_id: id === 'fresh' || id === 'nadia' ? null : `CUST-${id.toUpperCase()}`,
    hero_image: '/products/hero-theo.png', hero_alt: NAMES[id], hero_subheadline: 'Live profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  }
}

/** The stand-in server: one session, signed in only through the workshop sign-in. */
async function serve(page: Page) {
  const session = { user: null as string | null, persona: null as string | null }
  const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/assets/personas/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.alloc(0) }))
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/ports\/\d+/, '')
    const method = route.request().method()
    const body = method === 'POST' ? route.request().postDataJSON() ?? {} : {}
    if (path.endsWith('/api/auth/password/csrf')) return route.fulfill(json({ csrfToken: 'csrf' }))
    if (path.endsWith('/api/auth/password/workshop-sign-in')) {
      if (!(SHOPPERS as readonly string[]).includes(body.username)) {
        return route.fulfill(json({ detail: 'workshop_user_not_allowed' }, 403))
      }
      session.user = body.username
      return route.fulfill(json({ status: 'signed_in', username: body.username, signInMethod: 'workshop' }))
    }
    if (path.endsWith('/api/auth/me')) {
      return session.user
        ? route.fulfill(json({ user_id: `sub-${session.user}`, email: `${session.user}@pellier.example.com`, username: session.user, sign_in_method: 'workshop' }))
        : route.fulfill(json({ error: 'auth_failed' }, 401))
    }
    if (path.endsWith('/api/auth/logout')) {
      session.user = null
      return route.fulfill(json({ ok: true }))
    }
    if (path.includes('/api/auth/')) return route.fulfill(json({ error: 'refresh_failed' }, 401))
    if (path.endsWith('/api/user/preferences')) return route.fulfill(json({ preferences: null }))
    if (path.endsWith('/api/personas')) return route.fulfill(json(['fresh', 'nadia', ...SHOPPERS].map(profile)))
    if (path.endsWith('/api/persona/switch')) {
      session.persona = body.persona_id
      return route.fulfill(json({ session_id: `persona-${body.persona_id}-${'0'.repeat(32)}`, persona: profile(body.persona_id) }))
    }
    if (path.endsWith('/api/persona/current')) {
      return route.fulfill(json({ persona: session.persona && session.user ? profile(session.persona) : null }))
    }
    if (path.endsWith('/api/chat/stream')) {
      // The principal comes from the session, never from the request body.
      const principal = session.user
        ? { authenticated: true, customerId: `CUST-${session.user.toUpperCase()}`, signInMethod: 'workshop' }
        : { authenticated: false, customerId: null, signInMethod: null }
      const events = [
        { type: 'turn_start', turn_id: 'turn-' + 'b'.repeat(32), session_id: 's', principal },
        { type: 'content', content: 'Here is what I found.' },
        { type: 'complete', response: { response: 'Here is what I found.', products: [], suggestions: [], turn_id: 'turn-' + 'b'.repeat(32) } },
      ]
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('') })
    }
    if (path.endsWith('/api/products')) return route.fulfill(json([]))
    if (path.endsWith('/api/scenarios')) return route.fulfill(json({ scenarios: [] }))
    return route.fulfill(json({}))
  })
  return session
}

async function askAndReadPrincipal(page: Page): Promise<string> {
  const ask = page.getByTestId('pellier-hero-search')
  await ask.fill('Something warm for the evening')
  await ask.press('Enter')
  const drawer = page.getByTestId('chat-drawer')
  await expect(drawer).toBeVisible()
  const line = drawer.getByTestId('turn-principal').last()
  await expect(line).toBeVisible()
  const text = (await line.textContent()) ?? ''
  await drawer.getByRole('button', { name: 'Close Ask Pellier' }).click()
  return text.replace(/^Identity/, '')
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    localStorage.setItem('pellier-builder-view', 'on')
  })
})

test('choosing a shopper signs in, switching changes the principal, signing out clears it', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await serve(page)
  await page.goto('/')

  // The chooser: the four customers, never staff or the guest edit.
  const chooser = page.getByTestId('persona-concierge')
  await expect(chooser.getByRole('button')).toHaveCount(4)
  for (const id of SHOPPERS) await expect(page.getByTestId(`hero-profile-${id}`)).toBeVisible()
  await expect(page.getByTestId('hero-profile-nadia')).toHaveCount(0)
  await expect(page.getByTestId('persona-identity-boundary')).toHaveText(
    'Choosing a shopper signs you in with their demo account. Pellier trusts the signed token, not this choice.',
  )

  // Browsing without choosing stays signed out.
  expect(await askAndReadPrincipal(page)).toBe('Not signed in')

  // Choosing Theo signs Theo in; the next turn runs as Theo.
  await page.getByTestId('hero-profile-theo').click()
  await expect(page.getByTestId('persona-pill')).toContainText('Theo')
  expect(await askAndReadPrincipal(page)).toBe('Workshop sign-in, CUST-THEO')

  // Switching to Anna from the header signs Theo out and Anna in.
  await page.getByTestId('persona-pill').click()
  await page.getByTestId('persona-card-anna').click()
  await expect(page.getByTestId('persona-modal')).toHaveCount(0)
  await expect(page.getByTestId('persona-pill')).toContainText('Anna')
  expect(await askAndReadPrincipal(page)).toBe('Workshop sign-in, CUST-ANNA')

  // Signing out returns to the neutral store, with no principal. Sign-out
  // reloads the page once the server cleared the session.
  await page.getByTestId('persona-pill').click()
  const reloaded = page.waitForEvent('load')
  await page.getByTestId('persona-sign-out').click()
  await reloaded
  await expect(page.getByTestId('persona-concierge')).toBeVisible()
  expect(await askAndReadPrincipal(page)).toBe('Not signed in')
})
