import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

/** Read a source file from the project root, for structural assertions. */
function readSource(relative: string): string {
  return readFileSync(resolve(process.cwd(), relative), 'utf8')
}

vi.mock('./pages/PellierPage', () => ({
  default: () => <div>Storefront route</div>,
}))

vi.mock('./pages/ProductDetailPage', () => ({
  default: () => <div>Product detail route</div>,
}))

import { AppRoutes } from './App'

function LocationProbe() {
  const { pathname, search, hash } = useLocation()
  return <output data-testid="location">{`${pathname}${search}${hash}`}</output>
}

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('canonical application routes', () => {

  it('serves Stories as a real storefront destination', async () => {
    renderRoute('/storyboard')
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/storyboard')
    })
  })

  it('serves About as a real storefront destination', async () => {
    renderRoute('/about')
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/about')
    })
  })

  it('sends the storefront header to Stories and About, not the shop band', () => {
    const page = readSource('src/pages/PellierPage.tsx')
    const routes = page.match(/const NAV_ROUTES[^{]*\{([^}]*)\}/)?.[1] ?? ''
    expect(routes).toMatch(/stories:\s*'\/storyboard'/)
    expect(routes).toMatch(/storyboard:\s*'\/storyboard'/)
    expect(routes).toMatch(/about:\s*'\/about'/)
    expect(routes).not.toMatch(/(stories|about):\s*'\/#shop'/)
  })

  it('serves one piece at its own deep-linkable route', async () => {
    renderRoute('/product/11')

    expect(await screen.findByText('Product detail route')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/product/11')
  })

  // The inspection surface was removed. Its old paths, including bookmarks
  // in older guides, land on the storefront instead of a blank page.
  it.each(['/observatory', '/observatory/proof-board', '/labs', '/agent-trace'])(
    'sends the retired %s to the storefront',
    async (path) => {
      renderRoute(path)
      expect(await screen.findByText('Storefront route')).toBeInTheDocument()
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/)
    },
  )

})

describe('surface boundaries', () => {
  it('keeps the shopper chat drawer off the Operator console', () => {
    const source = readSource('src/App.tsx')
    expect(source).toContain('function ShopperChatSlot()')
    expect(source).toContain("if (pathname.startsWith('/operator')) return null")
    expect(source).toContain('<ShopperChatSlot />')
    // Mounted through the slot only, never directly.
    expect(source.match(/<ChatDrawer \/>/g)?.length).toBe(1)
  })

  // The shopper's Ask Pellier drawer was mounted on every route, so its
  // "Continue chat" pill floated over Pellier Operator whenever the browser held a
  // storefront thread. Operator is a different product with its own Concierge.

  it('lets the storefront reader resume following the latest reply', () => {
    const source = readSource('src/components/ChatDrawer.tsx')
    expect(source).toContain('followLatestRef')
    expect(source).toContain('Latest reply')
    expect(source).toContain('showLatest')
  })
})
