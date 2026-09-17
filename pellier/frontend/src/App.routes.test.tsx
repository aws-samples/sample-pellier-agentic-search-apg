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

vi.mock('./observatory/shell/ObservatoryFrame', async () => {
  const { Outlet } = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return {
    default: () => (
      <div>
        Observatory frame
        <Outlet />
      </div>
    ),
  }
})

vi.mock('./observatory/surfaces/observe/ObservatoryWorkbench', () => ({
  default: () => <div>Pellier Observatory workbench</div>,
}))

vi.mock('./observatory/surfaces/labs/LabsCatalog', () => ({
  default: () => <div>Governed Lab Collection</div>,
}))

vi.mock('./observatory/surfaces/observe/SessionsList', () => ({
  default: () => <div>Live Aurora sessions</div>,
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
  it('renders the governed lab collection at the canonical route', async () => {
    renderRoute('/observatory?turn=live#journey')

    expect(
      await screen.findByText('Governed Lab Collection'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/observatory?turn=live#journey',
    )
  })

  it('keeps the live request surface at its own workbench route', async () => {
    renderRoute('/observatory/workbench')

    expect(
      await screen.findByText('Pellier Observatory workbench'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/observatory/workbench',
    )
  })

  it('redirects old guide bookmarks to the matching Workbench scenario', async () => {
    renderRoute('/observatory/labs/grounded-inventory')

    expect(await screen.findByText('Pellier Observatory workbench')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/observatory/workbench?lab=grounded-inventory',
    )
  })

  it('keeps the old Labs collection deep link inside Observatory', async () => {
    renderRoute('/observatory/labs')

    expect(
      await screen.findByText('Governed Lab Collection'),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/observatory')
    })
  })

  it('serves Stories as a real storefront destination', async () => {
    renderRoute('/storyboard')
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/storyboard')
    })
  })

  it('returns retired supporting guide bookmarks to the Lab Collection', async () => {
    renderRoute('/observatory/guide/summary#cleanup')
    expect(await screen.findByText('Governed Lab Collection')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/observatory')
    expect(screen.getByTestId('location')).not.toHaveTextContent('/guide/')
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

  it('redirects the retired references surface into workbench resources', async () => {
    renderRoute('/observatory/references')

    expect(
      await screen.findByText('Pellier Observatory workbench'),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/observatory/workbench#resources',
      )
    })
  })

  it('serves one piece at its own deep-linkable route', async () => {
    renderRoute('/product/11')

    expect(await screen.findByText('Product detail route')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/product/11')
  })

  // Every path the surface has lived at. A rename sweep once rewrote this
  // table's inputs to the new path, leaving it asserting /observatory ->
  // /observatory: green, and blind to a redirect that pointed at itself.
  // These inputs are legacy by definition and must never be updated to the
  // current path — that is the whole point of the assertion.
  it.each([
    ['/agent-trace', '/observatory'],
    ['/agent-trace/proof-board', '/observatory/proof-board'],
    ['/pellier-labs', '/observatory'],
    ['/pellier-labs/tools', '/observatory/tools'],
    ['/labs', '/observatory'],
    ['/labs/proof-board?turn=live#managed', '/observatory/proof-board?turn=live#managed'],
  ])('redirects the retired %s to %s', async (path, expected) => {
    renderRoute(path)

    expect(await screen.findByText('Observatory frame')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(expected)
  })

  it('serves the current surface path without redirecting', async () => {
    renderRoute('/observatory/proof-board?turn=live#managed')

    expect(await screen.findByText('Observatory frame')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/observatory/proof-board?turn=live#managed',
    )
  })

  it('replaces the retired persona-journey fixture page with live sessions', async () => {
    renderRoute('/observatory/persona-journeys')

    expect(await screen.findByText('Observatory frame')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/observatory/sessions',
      ),
    )
  })
})

describe('surface boundaries', () => {
  // The shopper's Ask Pellier drawer was mounted on every route, so its
  // "Continue chat" pill floated over Pellier Operator whenever the browser held a
  // storefront thread. Operator is a different product with its own Concierge.
  it('keeps the shopper chat drawer off operational and evidence surfaces', () => {
    const source = readSource('src/App.tsx')
    expect(source).toContain('function ShopperChatSlot()')
    expect(source).toContain(
      "if (pathname.startsWith('/operator') || pathname.startsWith('/observatory')) return null",
    )
    expect(source).toContain('<ShopperChatSlot />')
    // Mounted through the slot only, never directly.
    expect(source.match(/<ChatDrawer \/>/g)?.length).toBe(1)
  })

  it('does not mount a competing concierge modal on the Observatory', () => {
    const source = readSource('src/App.tsx')
    expect(source).not.toContain('ObservatoryConciergeSlot')
    expect(source).not.toContain("import('./components/ConciergeModal')")
  })

  it('lets the storefront reader resume following the latest reply', () => {
    const source = readSource('src/components/ChatDrawer.tsx')
    expect(source).toContain('followLatestRef')
    expect(source).toContain('Latest reply')
    expect(source).toContain('showLatest')
  })
})
