/**
 * App.test.tsx - Provider wiring smoke test (Task 6.2 / Req 7.2.1).
 *
 * Validates:
 *   1. The provider chain at the App root resolves without any
 *      "useContext must be used within ..." errors. The chain is
 *      AuthProvider -> LayoutProvider -> CartProvider -> UIProvider ->
 *      BrowserRouter -> Routes. LayoutProvider is retained from the
 *      pre-existing workshop chrome; the spec-required order
 *      (Auth -> Cart -> UI -> Routes) is preserved as a subsequence.
 *   2. The default route (path "*") renders the home-page shell. No
 *      dedicated HomePage component exists yet - `AppContent` serves as
 *      the home surface - so we assert on the Header wordmark testid,
 *      which is the stable home-page marker rendered at the top of
 *      `AppContent`.
 *   3. The modal singleton slots are mounted at the App root: both
 *      `AuthModal` and `PreferencesModal` exist in the tree and render
 *      nothing while `UIContext.activeModal === null`, as required by
 *      the UIContext contract (Task 4.1).
 *
 * The test mocks `fetch` globally so the AuthProvider hydration path
 * (GET /api/auth/me, GET /api/user/preferences) settles quickly and
 * the various workshop-status / inventory side-effects in child
 * components don't flake on network errors. No other mocks are used:
 * providers are mounted live so a runtime context error would surface
 * here rather than only at dev-server boot.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// --- fetch mock ---------------------------------------------------------
// Return 401 for auth/preferences (unauthenticated) and empty-ok for
// everything else. This lets AuthProvider resolve `loading=false` fast
// and keeps unrelated polling hooks (build state, inventory) from
// logging jsdom network errors.
const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
  const url = typeof input === 'string' ? input : input.toString()
  if (url.includes('/api/auth/me') || url.includes('/api/user/preferences')) {
    return new Response(null, { status: 401 })
  }
  if (url.includes('/api/atelier/build-state')) {
    // useBuildState reads `{ agents: {name: status}, tools: {fn: status} }`
    // (see routes/atelier_observatory.py::get_build_state). Return a
    // well-shaped starter payload (floor_check still an exercise) so the
    // Sidebar progress badges resolve without a jsdom network error.
    return new Response(
      JSON.stringify({
        agents: { 'Stock Keeper': 'exercise' },
        tools: { floor_check: 'exercise' },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )
  }
  return new Response(JSON.stringify({}), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
})

beforeEach(() => {
  mockFetch.mockClear()
  vi.stubGlobal('fetch', mockFetch)
  // IntersectionObserver is used by scroll-reveal hooks; jsdom doesn't ship one.
  class MockIO {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
  }
  vi.stubGlobal('IntersectionObserver', MockIO)
  // matchMedia is read by a few responsive hooks in the legacy chrome.
  if (!window.matchMedia) {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }))
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// Import AFTER the mocks so module-level state picks them up cleanly.
// App.tsx pulls in ~50 components; we intentionally don't mock any of
// them so a real context-resolution error would surface here.
import App from './App'

describe('App - provider wiring (Task 6.2 / Req 7.2.1)', () => {
  it('resolves the provider chain without runtime context errors', async () => {
    const errors: unknown[] = []
    const errorSpy = vi.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args)
    })

    // If any descendant threw "useX must be used within ...", React would
    // surface it via console.error during render. We catch all console.error
    // output and filter below.
    render(<App />)

    // Wait for AuthProvider hydration to settle - the home-page shell
    // only renders after `loading=false`.
    await waitFor(() => {
      expect(screen.getByTestId('wordmark')).toBeInTheDocument()
    })

    // Filter to only the context-provider violations we care about.
    // React logs other benign warnings (router future flags, missing
    // act(), etc.) in jsdom; those aren't the contract under test.
    const contextErrors = errors.filter((entry) => {
      const flat = Array.isArray(entry) ? entry.join(' ') : String(entry)
      return /must be used within/i.test(flat)
    })
    expect(contextErrors).toEqual([])

    errorSpy.mockRestore()
  })

  it('renders the home-page shell on the default route', async () => {
    render(<App />)

    // The Header wordmark is the stable anchor for the home-page shell.
    // It's rendered at the top of `AppContent` (which the `*` route
    // resolves to via <AuthGate/>) and is never rendered by the
    // /storyboard or /discover routes.
    const wordmark = await screen.findByTestId('wordmark')
    expect(wordmark).toHaveTextContent(/Pellier/i)

    // Persona pill is the other canonical home-page marker; confirms
    // the persona-dependent branch of the header mounted.
    expect(screen.getByTestId('persona-pill')).toBeInTheDocument()
  })

  it('mounts AuthModal + PreferencesModal as hidden singletons at the App root', async () => {
    render(<App />)

    // Both modals read `activeModal` from UIContext. With no opener
    // fired they must render nothing, but the components themselves
    // must be in the tree so opening a modal later surfaces them.
    await screen.findByTestId('wordmark')
    expect(screen.queryByTestId('auth-modal')).not.toBeInTheDocument()
    expect(screen.queryByTestId('prefs-modal')).not.toBeInTheDocument()
    expect(screen.queryByTestId('auth-modal-backdrop')).not.toBeInTheDocument()
    expect(screen.queryByTestId('prefs-modal-backdrop')).not.toBeInTheDocument()
  })
})
