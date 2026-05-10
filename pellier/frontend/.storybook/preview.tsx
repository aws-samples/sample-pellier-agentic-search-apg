/**
 * Storybook preview — global decorators and parameters.
 *
 * Owned by task 7.2 in `.kiro/specs/pellier-storefront/tasks.md`.
 *
 * Provides:
 *   - Warm cream background matching the storefront design tokens
 *     (`--cream: #fbf4e8` from storefront.md).
 *   - Chromatic viewport presets for mobile / tablet / desktop
 *     (Req 5.2.1–5.2.3).
 *   - An AuthContext decorator whose default state is "signed out"; a
 *     story can opt in to "signed in + preferences" via
 *     `parameters.authState`.
 *   - Router + UIContext + CartContext providers so route-level stories
 *     (Storyboard, Discover) render without wrapping each story.
 *
 * This file imports `@storybook/react`, which is not yet in
 * `package.json`. Install with the other Storybook devDeps when turning
 * Chromatic on (see tests/visual-regression/README.md).
 */
import type { Preview } from '@storybook/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { CartProvider } from '../src/contexts/CartContext'
import { UIProvider } from '../src/contexts/UIContext'
import type { Preferences } from '../src/services/types'
import '../src/index.css'

/**
 * Viewport presets for Chromatic. The three widths come from Req 5.2:
 *   - mobile  <768px   → 375px (iPhone-class)
 *   - tablet  ≥768px   → 768px (iPad portrait)
 *   - desktop ≥1024px  → 1280px (laptop baseline)
 */
const CHROMATIC_VIEWPORTS = {
  mobile: {
    name: 'Mobile (375px)',
    styles: { width: '375px', height: '812px' },
  },
  tablet: {
    name: 'Tablet (768px)',
    styles: { width: '768px', height: '1024px' },
  },
  desktop: {
    name: 'Desktop (1280px)',
    styles: { width: '1280px', height: '800px' },
  },
}

/**
 * Story-level parameter hatch for auth state. Stories that need
 * "signed in" coverage set:
 *
 *   parameters: {
 *     authState: {
 *       user: { sub: 'u1', email: 'ava@example.com', givenName: 'Ava' },
 *       preferences: { vibe: ['minimal'], colors: [], occasions: [], categories: [] },
 *     },
 *   }
 */
interface AuthStateParam {
  user: {
    sub: string
    email: string
    givenName?: string
  } | null
  preferences: Preferences | null
}

/**
 * Minimal stand-in for `AuthProvider` that reads story parameters rather
 * than hitting `/api/auth/me`. The real `AuthProvider` does a fetch on
 * mount; we don't want that in a Storybook sandbox.
 *
 * Components inside stories MUST import `useAuth` from the same file
 * they use in the app (`contexts/AuthContext`); that hook reads from
 * the context provided here. For the scaffolding phase we re-create a
 * matching context shape so the module graph is deterministic. When
 * Storybook is actually wired in, replace this shim with the real
 * `AuthProvider` wrapped around a fetch mock (MSW is the usual choice).
 */
function MockAuthProvider({
  authState,
  children,
}: {
  authState: AuthStateParam
  children: ReactNode
}) {
  // We lazy-import the real context module so that flipping between
  // "with Storybook installed" and "without" doesn't change the import
  // graph in the app. The real `AuthContext` export lives at
  // `../src/contexts/AuthContext`.
  //
  // Until Storybook is installed, this module is not evaluated.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { AuthProvider } = require('../src/contexts/AuthContext') as {
    AuthProvider: React.ComponentType<{ children: ReactNode }>
  }
  // The real provider fetches on mount; for snapshots we render it
  // with a stubbed window.fetch so the initial state lands on the
  // story-requested auth snapshot before the first paint Chromatic
  // captures.
  if (typeof window !== 'undefined') {
    const originalFetch = window.fetch
    window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/api/auth/me')) {
        if (authState.user === null) {
          return new Response(JSON.stringify({ error: 'auth_failed' }), {
            status: 401,
          })
        }
        return new Response(JSON.stringify({
          user_id: authState.user.sub,
          email: authState.user.email,
          given_name: authState.user.givenName ?? '',
        }), { status: 200, headers: { 'content-type': 'application/json' } })
      }
      if (url.endsWith('/api/user/preferences')) {
        return new Response(JSON.stringify({
          preferences: authState.preferences,
        }), { status: 200, headers: { 'content-type': 'application/json' } })
      }
      // Products / inventory / search requests fall through to the
      // original fetch, which will 404 in the Storybook sandbox. Add
      // MSW handlers here when moving past scaffolding.
      return originalFetch(input, init)
    }) as typeof window.fetch
  }
  return <AuthProvider>{children}</AuthProvider>
}

const preview: Preview = {
  parameters: {
    layout: 'fullscreen',
    backgrounds: {
      default: 'cream',
      values: [
        { name: 'cream', value: '#fbf4e8' },
        { name: 'ink', value: '#2d1810' },
      ],
    },
    viewport: {
      viewports: CHROMATIC_VIEWPORTS,
    },
    chromatic: {
      // Default snapshot coverage for every story; individual stories
      // can narrow or widen this list.
      viewports: [375, 768, 1280],
      // Disable snapshot animations at capture time so the Ken Burns
      // zoom and parallax fade don't produce flaky diffs.
      pauseAnimationAtEnd: true,
      delay: 300,
    },
  },

  decorators: [
    (Story, ctx) => {
      const authState: AuthStateParam = (ctx.parameters.authState as AuthStateParam) ?? {
        user: null,
        preferences: null,
      }
      return (
        <MemoryRouter initialEntries={[ctx.parameters.route ?? '/']}>
          <MockAuthProvider authState={authState}>
            <CartProvider>
              <UIProvider>
                <Story />
              </UIProvider>
            </CartProvider>
          </MockAuthProvider>
        </MemoryRouter>
      )
    },
  ],
}

export default preview
