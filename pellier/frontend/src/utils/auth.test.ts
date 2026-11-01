/**
 * utils/auth.test.ts — Task 5.1 verification.
 *
 * Covers the sign-in navigation helpers: `openSignInChooser` routes to
 * `/signin?returnTo=...`, and `redirectToSignIn` sends the shopper there.
 *
 * We avoid mounting the React context just for these helpers; the module
 * under test is pure navigation.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

// --- Helpers ----------------------------------------------------------

/**
 * Install a mutable `window.location` so we can assert against the URL
 * the module navigates to. jsdom's location is read-only by default;
 * re-defining the property is the least-bad way to observe navigation.
 */
function installLocation(initial: { pathname?: string; search?: string } = {}) {
  const assign = vi.fn()
  const mockLocation = {
    assign,
    pathname: initial.pathname ?? '/',
    search: initial.search ?? '',
    hash: '',
    href: `http://localhost${initial.pathname ?? '/'}${initial.search ?? ''}`,
    origin: 'http://localhost',
  }
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: mockLocation,
    writable: true,
  })
  return { assign }
}

// --- openSignInChooser ------------------------------------------------

describe('openSignInChooser', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('routes to /signin?returnTo=<current path+search> by default', async () => {
    const { assign } = installLocation({ pathname: '/discover', search: '?x=1' })
    const { openSignInChooser } = await import('./auth')

    openSignInChooser()

    expect(assign).toHaveBeenCalledTimes(1)
    const [url] = assign.mock.calls[0]
    expect(url).toBe(`/signin?returnTo=${encodeURIComponent('/discover?x=1')}`)
  })

  it('honors an explicit returnTo override', async () => {
    const { assign } = installLocation({ pathname: '/unused', search: '' })
    const { openSignInChooser } = await import('./auth')

    openSignInChooser({ returnTo: '/cart?step=checkout' })

    expect(assign).toHaveBeenCalledTimes(1)
    const [url] = assign.mock.calls[0]
    expect(url).toBe(`/signin?returnTo=${encodeURIComponent('/cart?step=checkout')}`)
  })
})

// --- redirectToSignIn -------------------------------------------------

describe('redirectToSignIn', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('navigates to /api/auth/signin?provider=<p>&returnTo=<...>', async () => {
    const { assign } = installLocation({ pathname: '/', search: '' })
    const { redirectToSignIn } = await import('./auth')

    redirectToSignIn('google', { returnTo: '/home' })

    expect(assign).toHaveBeenCalledTimes(1)
    const [url] = assign.mock.calls[0]
    expect(url).toBe(
      `/api/auth/signin?provider=${encodeURIComponent('google')}&returnTo=${encodeURIComponent('/home')}`,
    )
  })
})
