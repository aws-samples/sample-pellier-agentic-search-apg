/**
 * The home grid pages through the whole catalog, twelve pieces a page.
 *
 * The real grid, pager and router run here; only the network is scripted, as
 * a catalog of 100 pieces that answers `GET /api/products?page=` the way the
 * route does: the edit first, then the rest, each piece once. The grid draws
 * exactly what each page returns, in its order, from one read per page.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HomeGrid from './HomeGrid'

const personaState = vi.hoisted(() => ({
  persona: null as null | { id: string; edit: string; display_name: string },
}))

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona: personaState.persona }),
}))
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ prefsVersion: 0 }),
}))

const ANNA = { id: 'anna', edit: 'anna', display_name: 'Anna Lindqvist' }
const EDITS: Record<string, number[]> = {
  fresh: [3, 1, 2, 4, 5, 6, 7, 8, 9, 10, 85, 70],
  anna: [21, 23, 27, 26, 29, 22, 25, 24, 28, 30, 62, 78],
}
const PAGE_SIZE = 12
const TOTAL = 100

function card(id: number) {
  return {
    id, name: `Piece ${id}`, brand: 'Pellier', color: 'Oat', price: 40, rating: 4.5, reviewCount: 9,
    category: 'Home', imageUrl: `/products/${id}.webp`, tags: [], quantity: 9, warehouses: [],
  }
}

/** The route's order: the edit, then every other piece. */
function catalogOrder(edit: string): number[] {
  const first = EDITS[edit] ?? []
  const rest = Array.from({ length: TOTAL }, (_, index) => index + 1).filter(id => !first.includes(id))
  return [...first, ...rest]
}

let reads: URL[] = []

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function serveCatalog(input: RequestInfo | URL) {
  const url = new URL(String(input), 'http://localhost')
  reads.push(url)
  const page = Number(url.searchParams.get('page'))
  const size = Number(url.searchParams.get('page_size'))
  const ids = catalogOrder(url.searchParams.get('persona') ?? '').slice((page - 1) * size, page * size)
  if (ids.length === 0) return respond({ detail: 'page_not_found' }, 404)
  return respond({ products: ids.map(card), page, pageSize: size, total: TOTAL, pages: Math.ceil(TOTAL / size) })
}

let location = ''
function LocationProbe() {
  const current = useLocation()
  location = `${current.pathname}${current.search}`
  return null
}

function tree(path: string) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<><HomeGrid /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  )
}

function renderAt(path = '/') {
  return render(tree(path))
}

function cardIds(): number[] {
  return Array.from(screen.getByTestId('home-grid').querySelectorAll('[data-testid^="product-card-"]'))
    .map(node => node.getAttribute('data-testid') ?? '')
    .filter(id => /^product-card-\d+$/.test(id))
    .map(id => Number(id.replace('product-card-', '')))
}

async function showsPage(range: string) {
  await waitFor(() => expect(screen.getByTestId('home-grid-range')).toHaveTextContent(range))
}

function pager() {
  return within(screen.getByTestId('home-pager'))
}

describe('the home grid, page by page', () => {
  const scrollIntoView = Element.prototype.scrollIntoView
  let scrolled = vi.fn()
  beforeEach(() => {
    reads = []
    personaState.persona = null
    scrolled = vi.fn()
    Element.prototype.scrollIntoView = scrolled
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => serveCatalog(input)))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    Element.prototype.scrollIntoView = scrollIntoView
  })

  it('opens signed out on "This week at Pellier", twelve of the 100 pieces', async () => {
    renderAt()
    await showsPage('1–12 of 100')
    expect(screen.getByTestId('home-grid-title')).toHaveTextContent('This week at Pellier')
    expect(screen.getByTestId('home-grid-count')).toHaveTextContent(/^100 pieces$/)
    expect(cardIds()).toEqual(EDITS.fresh)
    expect(reads).toHaveLength(1)
    expect(Object.fromEntries(reads[0].searchParams)).toEqual({ persona: 'fresh', page: '1', page_size: '12' })

    const pages = pager().getAllByTestId('home-pager-page')
    expect(pages.map(link => link.textContent)).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9'])
    expect(pages[0]).toHaveAttribute('aria-current', 'page')
    expect(pages.slice(1).every(link => !link.hasAttribute('aria-current'))).toBe(true)
    expect(pages[1]).toHaveAccessibleName('Page 2')
    expect(screen.getByRole('navigation', { name: 'Pages of the collection' })).toBeInTheDocument()
    expect(pager().getByTestId('home-pager-status')).toHaveTextContent('Page 1 of 9')
  })

  it('moves to page 2: "More from Pellier", the next twelve, none from page 1, at the top of the grid', async () => {
    renderAt()
    await showsPage('1–12 of 100')
    const first = cardIds()

    fireEvent.click(pager().getByTestId('home-pager-next'))
    expect(location).toBe('/?page=2')
    await showsPage('13–24 of 100')
    expect(screen.getByTestId('home-grid-title')).toHaveTextContent('More from Pellier')
    const second = cardIds()
    expect(second).toHaveLength(12)
    expect(second.filter(id => first.includes(id))).toEqual([])
    expect(pager().getAllByTestId('home-pager-page')[1]).toHaveAttribute('aria-current', 'page')
    expect(Object.fromEntries(reads[1].searchParams)).toMatchObject({ persona: 'fresh', page: '2' })
    expect(reads).toHaveLength(2)

    // The grid's top, not the page's, and the heading holds the focus.
    expect(scrolled).toHaveBeenCalledWith(expect.objectContaining({ block: 'start' }))
    expect(scrolled.mock.contexts[0]).toBe(screen.getByTestId('home-collection'))
    expect(document.activeElement).toBe(screen.getByTestId('home-grid-title'))
  })

  it('shows every piece exactly once across the nine pages, the last holding four', async () => {
    renderAt()
    await showsPage('1–12 of 100')
    const seen: number[] = [...cardIds()]
    for (let page = 2; page <= 9; page += 1) {
      fireEvent.click(pager().getByRole('link', { name: `Page ${page}` }))
      const first = (page - 1) * PAGE_SIZE + 1
      await showsPage(`${first}–${Math.min(first + PAGE_SIZE - 1, TOTAL)} of 100`)
      seen.push(...cardIds())
    }
    expect(cardIds()).toHaveLength(4)
    expect(seen).toHaveLength(100)
    expect(new Set(seen).size).toBe(100)
    expect(seen).toEqual(catalogOrder('fresh'))
    expect(reads).toHaveLength(9)
  })

  it('keeps Previous inert on page 1 and Next inert on the last page', async () => {
    renderAt()
    await showsPage('1–12 of 100')
    const previous = pager().getByTestId('home-pager-prev')
    expect(previous).toHaveAttribute('aria-disabled', 'true')
    expect(previous).not.toHaveAttribute('href')
    expect(pager().getByTestId('home-pager-next')).toHaveAttribute('href', '/?page=2')
    fireEvent.click(previous)
    expect(location).toBe('/')

    fireEvent.click(pager().getByRole('link', { name: 'Page 9' }))
    await showsPage('97–100 of 100')
    const next = pager().getByTestId('home-pager-next')
    expect(next).toHaveAttribute('aria-disabled', 'true')
    expect(next).not.toHaveAttribute('href')
    fireEvent.click(next)
    expect(location).toBe('/?page=9')
    expect(pager().getByTestId('home-pager-prev')).toHaveAttribute('href', '/?page=8')
    expect(pager().getByTestId('home-pager-status')).toHaveTextContent('Page 9 of 9')

    // Back to page 1 drops the parameter: the bare home is page 1.
    fireEvent.click(pager().getByRole('link', { name: 'Page 1' }))
    expect(location).toBe('/')
    await showsPage('1–12 of 100')
  })

  it("titles a signed-in shopper's first page with their edit, then pages the rest", async () => {
    personaState.persona = ANNA
    renderAt()
    await showsPage('1–12 of 100')
    expect(screen.getByTestId('home-grid-title')).toHaveTextContent("Anna's edit")
    expect(cardIds()).toEqual(EDITS.anna)
    expect(reads[0].searchParams.get('persona')).toBe('anna')

    fireEvent.click(pager().getByTestId('home-pager-next'))
    await showsPage('13–24 of 100')
    expect(screen.getByTestId('home-grid-title')).toHaveTextContent('More from Pellier')
    expect(cardIds().filter(id => EDITS.anna.includes(id))).toEqual([])
  })

  it('opens on the page the URL names', async () => {
    renderAt('/?page=3')
    await showsPage('25–36 of 100')
    expect(pager().getAllByTestId('home-pager-page')[2]).toHaveAttribute('aria-current', 'page')
    expect(reads.map(url => url.searchParams.get('page'))).toEqual(['3'])
    // Arriving by URL (or Back) leaves the scroll to the router's restore.
    expect(scrolled).not.toHaveBeenCalled()
  })

  it('lands on page 1 from a page past the end', async () => {
    renderAt('/?page=12')
    await waitFor(() => expect(location).toBe('/'))
    await showsPage('1–12 of 100')
    expect(reads.map(url => url.searchParams.get('page'))).toEqual(['12', '1'])
  })

  it('starts a new shopper on page 1', async () => {
    const view = renderAt('/?page=4')
    await showsPage('37–48 of 100')
    personaState.persona = ANNA
    act(() => view.rerender(tree('/?page=4')))
    await waitFor(() => expect(location).toBe('/'))
    await showsPage('1–12 of 100')
    expect(screen.getByTestId('home-grid-title')).toHaveTextContent("Anna's edit")
  })

  it('says the collection is unavailable when a page cannot be read, and reads it again on request', async () => {
    let fail = true
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (fail ? respond({}, 503) : serveCatalog(input))))
    renderAt()
    expect(await screen.findByRole('alert')).toHaveTextContent('We couldn’t load the latest pieces.')
    expect(screen.queryByTestId('home-grid')).toBeNull()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Reload collection' }))
    await showsPage('1–12 of 100')
  })
})
