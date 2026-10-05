/**
 * The page grid follows the Ask Pellier turn, from the same stream events.
 *
 * The real storefront page, home bar, dock, chat hook and results context
 * run here; only the network is scripted: the chat stream is fed one event at
 * a time, and `/api/products` answers the store edit and the cards for the
 * ids a search carried. The page never asks for anything but those ids.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UIProvider } from '../contexts/UIContext'
import { StoreResultsProvider } from '../contexts/StoreResultsContext'
import { writeBuilderView } from './turn/preferences'
import ChatDrawer from './ChatDrawer'
import Wordmark from './Wordmark'
import PellierPage from '../pages/PellierPage'

const stream = vi.hoisted(() => ({
  turns: [] as Array<{
    emit: (event: Record<string, unknown>) => void
    finish: (response: Record<string, unknown>) => void
    fail: (error: unknown) => void
  }>,
}))

vi.mock('../services/chat', async importOriginal => {
  const actual = await importOriginal<typeof import('../services/chat')>()
  return {
    ...actual,
    checkBackendHealth: vi.fn(async () => true),
    sendChatMessageStreaming: vi.fn(
      (_text: string, _history: unknown, onEvent: (event: Record<string, unknown>) => void) =>
        new Promise((resolve, reject) => {
          stream.turns.push({ emit: onEvent, finish: resolve, fail: reject })
        }),
    ),
  }
})
vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({ persona: null, switchPersona: vi.fn(), switching: false, signOut: vi.fn() }),
}))
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ prefsVersion: 0 }),
  useOptionalAuth: () => null,
}))
vi.mock('../contexts/LayoutContext', () => ({ useLayout: () => ({ guardrailsEnabled: false }) }))
vi.mock('../contexts/CartContext', () => ({
  useCart: () => ({ items: [], addToCart: vi.fn(), setCartOpen: vi.fn(), cartOpen: false }),
}))
vi.mock('./Header', () => ({ default: () => null }))
vi.mock('./Footer', () => ({ default: () => null }))
vi.mock('./PellierApproach', () => ({ default: () => null }))
vi.mock('./PellierServiceStrip', () => ({ default: () => null }))
vi.mock('./PellierSpotlight', () => ({ default: () => null }))
vi.mock('./PellierWelcome', () => ({ default: () => null }))

function card(id: number, name: string, quantity = 9) {
  return {
    id, name, brand: 'Pellier', color: 'Sand', price: 40, rating: 4.7, reviewCount: 20,
    category: 'Home', imageUrl: `/products/${id}.webp`, tags: [], quantity, warehouses: [],
  }
}

const CATALOG = new Map([
  [31, card(31, 'Stoneware Pour-Over Set')],
  [36, card(36, 'Ceramic Tumblers')],
  [22, card(22, 'Linen Napkins, Set of 4')],
  [65, card(65, 'Stoneware Mugs, Set of 2')],
  [12, card(12, 'Hadley Linen Shirt')],
  [3, card(3, 'Store Edit Feature')],
  [4, card(4, 'Store Edit Piece')],
])
const STORE_EDIT = [CATALOG.get(3), CATALOG.get(4)]
let idReads: string[] = []

function respond(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

const ANNA_QUESTION = 'A housewarming gift, in stock, under $100, no candles.'
const ROUTE_SHOPPING = {
  type: 'step', id: 'route', label: 'Understanding your request', status: 'done',
  finding: 'Sent to the Shopping agent', tags: ['Router'],
  builder: { tool: null, intent: 'shopping', agent: 'Shopping agent' },
}
const ROUTE_SUPPORT = { ...ROUTE_SHOPPING, finding: 'Sent to the Support agent', builder: { tool: null, intent: 'support', agent: 'Support agent' } }
const SEARCH_RUNNING = {
  type: 'step', id: 'step-1', label: 'Searching the catalog in Aurora', status: 'running',
  tags: ['Aurora'], builder: { tool: 'search_products' },
}
const LIMITS = [
  { kind: 'budget', label: 'Under $100', origin: 'stated' },
  { kind: 'stock', label: 'In stock', origin: 'stated' },
  { kind: 'exclusions', value: 'candle', label: 'No candles', origin: 'stated' },
]
const FILTERS = {
  kept: 64, of: 100, removed: { budget: 31, stock: 1, exclusions: 4 },
  excluded: [{ value: 'candle', count: 4, noun: 'candles' }],
}
const RANKING = {
  available: true, rail: 'in-process', method: 'hybrid+rerank', rrf_k: 60, rerank_pool: 15,
  arms: { full_text: 20, vector: 20, fused: 31 }, filters: FILTERS,
  rows: [{ product_id: '36', name: 'Ceramic Tumblers', fts_rank: 17, vec_rank: 2, similarity: 0.76, rrf_score: 0.0291, rerank_score: 0.84, before: 2, after: 1, moved: 1 }],
}

interface SearchDoneOptions {
  id?: string
  limits?: unknown[]
  filters?: unknown
  ranking?: unknown
  note?: string
}

function searchDone(ids: string[], { id = 'step-1', limits = LIMITS, filters = FILTERS, ranking = RANKING, note }: SearchDoneOptions = {}) {
  return {
    type: 'step', id, label: 'Searching the catalog in Aurora', status: 'done',
    finding: `${ids.length} found`, tags: ['Aurora'],
    builder: { tool: 'search_products', rail: 'in-process', ranking },
    results: { available: true, rail: 'in-process', product_ids: ids, count: ids.length, limits, filters, ...(note ? { note } : {}) },
  }
}

const COMPLETE = { response: 'Start with the Ceramic Tumblers at $40.', products: [], success: true }

function Storefront() {
  return (
    <MemoryRouter>
      <UIProvider>
        <StoreResultsProvider>
          <Wordmark />
          <PellierPage />
          <ChatDrawer />
        </StoreResultsProvider>
      </UIProvider>
    </MemoryRouter>
  )
}

function latestTurn() {
  return stream.turns[stream.turns.length - 1]
}

async function emit(...events: Array<Record<string, unknown>>) {
  await act(async () => {
    for (const event of events) latestTurn().emit(event)
  })
}

async function finish(response: Record<string, unknown> = COMPLETE) {
  await act(async () => {
    latestTurn().finish(response)
  })
}

async function askFromTheHomeBar(question: string) {
  const bar = await screen.findByTestId('pellier-hero-search')
  fireEvent.change(bar, { target: { value: question } })
  fireEvent.submit(bar.closest('form') as HTMLFormElement)
  await waitFor(() => expect(stream.turns.length).toBeGreaterThan(0))
}

async function askInTheDock(question: string) {
  const count = stream.turns.length
  const input = screen.getByLabelText('Message Pellier')
  fireEvent.change(input, { target: { value: question } })
  fireEvent.keyDown(input, { key: 'Enter' })
  await waitFor(() => expect(stream.turns.length).toBe(count + 1))
}

function gridNames(): string[] {
  const grid = screen.getByTestId('results-grid')
  return within(grid).getAllByRole('heading', { level: 3 }).map(heading => heading.textContent ?? '')
}

/** The names of the cards tagged "Pellier's pick", in grid order. */
function pickNames(): string[] {
  const grid = screen.getByTestId('results-grid')
  return Array.from(grid.querySelectorAll('[data-pick="true"]'))
    .map(card => card.querySelector('h3')?.textContent ?? '')
}

/** The answer's cards in the dock ("Pulled for you"), in their order. */
function dockCardNames(): string[] {
  const dock = screen.getByTestId('chat-drawer')
  return Array.from(dock.querySelectorAll('.pa-name')).map(name => name.textContent ?? '')
}

describe('the results view', () => {
  beforeEach(() => {
    stream.turns = []
    idReads = []
    localStorage.clear()
    sessionStorage.clear()
    writeBuilderView(false)
    // jsdom has no layout: the dock's scrolling is a no-op here.
    Element.prototype.scrollTo = vi.fn() as unknown as Element['scrollTo']
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/api/products') && url.searchParams.has('ids')) {
        const ids = url.searchParams.get('ids') ?? ''
        idReads.push(ids)
        return respond(ids.split(',').filter(Boolean).map(id => CATALOG.get(Number(id))).filter(Boolean))
      }
      if (url.pathname.endsWith('/api/products')) return respond(STORE_EDIT)
      if (url.pathname.includes('/api/agent/session/')) return respond({ turns: [] })
      return respond({})
    }))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    writeBuilderView(false)
  })

  it('appears on submit with a skeleton and the stream status, then the grid in the evidence order', async () => {
    render(<Storefront />)
    expect(await screen.findByTestId('home-grid')).toHaveTextContent('Store Edit Feature')

    await askFromTheHomeBar(ANNA_QUESTION)
    expect(screen.getByTestId('results-title')).toHaveTextContent(`Results for “${ANNA_QUESTION}”`)
    expect(screen.getByTestId('results-skeleton')).toBeInTheDocument()
    expect(screen.getByTestId('pellier-hero')).toHaveAttribute('data-compact', 'true')

    await emit(ROUTE_SHOPPING, SEARCH_RUNNING)
    const view = screen.getByTestId('results-view')
    expect(within(view).getByTestId('turn-status')).toHaveTextContent('Searching the catalog in Aurora')

    await emit(searchDone(['36', '22', '31']))
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers', 'Linen Napkins, Set of 4', 'Stoneware Pour-Over Set']))
    expect(idReads).toEqual(['36,22,31'])
    // The count describes the grid below it; "Kept 64 of 100" is the panel's.
    expect(screen.getByTestId('results-count')).toHaveTextContent(/^3 pieces$/)
    expect(screen.getAllByTestId('results-limit').map(tag => tag.textContent)).toEqual([
      'Under $100', 'In stock', 'No candles',
    ])

    await finish()
    expect(gridNames()).toHaveLength(3)
    expect(within(screen.getByTestId('results-view')).queryByTestId('turn-status')).toBeNull()
  })

  it('marks a limit carried from an earlier message as from earlier', async () => {
    render(<Storefront />)
    await askFromTheHomeBar('Which of those for a small kitchen?')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['65'], {
      limits: [
        { kind: 'budget', label: 'Under $100', origin: 'carried' },
        { kind: 'stock', label: 'In stock', origin: 'stated' },
      ],
    }))
    const tags = await screen.findAllByTestId('results-limit')
    expect(tags[0]).toHaveTextContent('Under $100, from earlier')
    expect(tags[0]).toHaveAttribute('data-origin', 'carried')
    expect(tags[1]).not.toHaveTextContent('from earlier')
  })

  it('marks a limit the shopper never stated as added by Pellier', async () => {
    render(<Storefront />)
    await askFromTheHomeBar('A gift for a friend')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['65'], {
      limits: [
        { kind: 'budget', label: 'Under $50', origin: 'agent' },
        { kind: 'stock', label: 'In stock', origin: 'stated' },
      ],
    }))
    const tags = await screen.findAllByTestId('results-limit')
    expect(tags[0]).toHaveTextContent('Under $50, added by Pellier')
    expect(tags[0]).toHaveAttribute('data-origin', 'agent')
    expect(tags[1]).toHaveTextContent(/^In stock$/)
  })

  it('keeps the question in the folded home bar, from the bar or the dock', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    const bar = screen.getByTestId('pellier-hero-search')
    expect(bar).toHaveValue(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36']))
    await finish()
    expect(bar).toHaveValue(ANNA_QUESTION)

    await askInTheDock('Something in linen for the trip')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING)
    expect(screen.getByTestId('pellier-hero-search')).toHaveValue('Something in linen for the trip')
  })

  it('replaces the grid with a follow-up search typed in the dock, and a support turn leaves it', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36', '22']))
    await finish()
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers', 'Linen Napkins, Set of 4']))

    await askInTheDock('Something in linen for the trip')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING)
    expect(screen.getByTestId('results-skeleton')).toBeInTheDocument()
    await emit(searchDone(['12']))
    await finish()
    await waitFor(() => expect(gridNames()).toEqual(['Hadley Linen Shirt']))
    expect(screen.getByTestId('results-title')).toHaveTextContent('Something in linen for the trip')

    await askInTheDock('Where is my order?')
    await emit(ROUTE_SUPPORT, {
      type: 'step', id: 'step-1', label: 'Reading your orders', status: 'running', tags: ['Aurora'],
      builder: { tool: 'get_orders' },
    })
    expect(gridNames()).toEqual(['Hadley Linen Shirt'])
    expect(screen.queryByTestId('results-skeleton')).toBeNull()
    await finish()
    expect(gridNames()).toEqual(['Hadley Linen Shirt'])
    expect(screen.getByTestId('results-title')).toHaveTextContent('Something in linen for the trip')
  })

  it('returns to the store on a support question from the store', async () => {
    render(<Storefront />)
    await screen.findByTestId('home-grid')
    await askFromTheHomeBar('Where is my order?')
    await emit(ROUTE_SUPPORT)
    expect(screen.queryByTestId('results-view')).toBeNull()
    expect(screen.getByTestId('home-grid')).toBeVisible()
    await finish()
    expect(screen.queryByTestId('results-view')).toBeNull()
  })

  it('shows the whole store again without touching the conversation', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36']))
    await finish()
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers']))
    const turnsBefore = stream.turns.length

    fireEvent.click(screen.getByTestId('results-clear'))
    expect(screen.queryByTestId('results-view')).toBeNull()
    expect(screen.getByTestId('home-grid')).toBeVisible()
    expect(screen.getByTestId('pellier-hero')).toHaveAttribute('data-compact', 'false')
    // The conversation is untouched: the question and its answer are still in the dock.
    const dock = screen.getByTestId('chat-drawer')
    expect(within(dock).getByText(ANNA_QUESTION)).toBeInTheDocument()
    expect(stream.turns.length).toBe(turnsBefore)
  })

  it('names what the limits left out when nothing fits', async () => {
    render(<Storefront />)
    await askFromTheHomeBar('A candle under $5')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone([], {
      filters: {
        kept: 0, of: 100, removed: { budget: 96, exclusions: 4 },
        excluded: [{ value: 'candle', count: 4, noun: 'candles' }],
      },
    }))
    await finish()
    const empty = await screen.findByTestId('results-empty')
    expect(empty).toHaveTextContent('Nothing fits all of that right now.')
    expect(empty).toHaveTextContent('Left out: 96 over budget, 4 candles.')
    expect(screen.getByTestId('results-count')).toHaveTextContent(/^0 pieces$/)
    expect(idReads).toEqual([])
  })

  it('keeps the previous grid and says so calmly when a turn fails', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36']))
    await finish()
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers']))

    await askInTheDock('And something for the bath?')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING)
    await act(async () => {
      latestTurn().fail(new Error('service_unavailable'))
    })
    await waitFor(() => expect(screen.getByTestId('results-failed')).toBeInTheDocument())
    expect(gridNames()).toEqual(['Ceramic Tumblers'])
  })

  it('says calmly that the store is as it was when a turn fails from the store', async () => {
    render(<Storefront />)
    await screen.findByTestId('home-grid')
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING)
    await act(async () => {
      latestTurn().fail(new Error('service_unavailable'))
    })
    const notice = await screen.findByTestId('results-failed-store')
    expect(notice).toHaveTextContent('That request did not finish. The store is as it was.')
    expect(screen.queryByTestId('results-view')).toBeNull()
    expect(screen.getByTestId('home-grid')).toBeVisible()
  })

  it('keeps a Builder-only note out of shopper copy and shows it in the panel with Builder view on', async () => {
    const note = 'Read from the retrieval receipt: no filter counts, and no record of which limits were kept from earlier'
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36', '22'], { filters: null, note }))
    await finish()
    await waitFor(() => expect(gridNames()).toHaveLength(2))
    const view = screen.getByTestId('results-view')
    expect(view).not.toHaveTextContent('retrieval receipt')
    expect(screen.getByTestId('results-count')).toHaveTextContent(/^2 pieces$/)

    act(() => writeBuilderView(true))
    const panel = await screen.findByTestId('ranking-panel')
    expect(within(panel).getByTestId('ranking-results-note')).toHaveTextContent(note)
    expect(screen.queryByTestId('results-note')).toBeNull()
  })

  it('shows two searches at once as two steps, and the page the one the answer named', async () => {
    const otherRanking = { ...RANKING, rows: [{ ...RANKING.rows[0], product_id: '12', name: 'Hadley Linen Shirt' }] }
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(
      ROUTE_SHOPPING,
      SEARCH_RUNNING,
      { ...SEARCH_RUNNING, id: 'step-2' },
      // The second search finishes first; each step carries only its own evidence.
      searchDone(['12', '65'], { id: 'step-2', ranking: otherRanking }),
      searchDone(['36', '22']),
    )
    await finish({
      ...COMPLETE,
      response: 'The Linen Napkins, Set of 4 at $44 are the gift.',
      products: [{ id: 22, name: 'Linen Napkins, Set of 4', price: 44 }],
    })
    // The answer named the napkins, from the first search: the page shows that
    // search, led by the napkins.
    await waitFor(() => expect(gridNames()).toEqual(['Linen Napkins, Set of 4', 'Ceramic Tumblers']))

    act(() => writeBuilderView(true))
    const dock = screen.getByTestId('chat-drawer')
    const fold = within(dock).queryByTestId('turn-fold')
    if (fold) fireEvent.click(fold)
    const searches = within(dock).getAllByTestId('turn-step').filter(step => step.textContent?.includes('Searching the catalog'))
    expect(searches).toHaveLength(2)
    const summaries = within(dock).getAllByTestId('ranking-summary')
    expect(summaries.map(summary => summary.textContent)).toEqual([
      expect.stringContaining('see the table above the results'),
      expect.stringContaining('show the table'),
    ])
    // The second step opens its own ranking in place, not the page's.
    fireEvent.click(summaries[1])
    const inPlace = within(dock).getByTestId('ranking-panel')
    expect(inPlace).toHaveTextContent('Hadley Linen Shirt')
    expect(within(screen.getByTestId('results-view')).getByTestId('ranking-panel')).toHaveTextContent('Ceramic Tumblers')
  })

  it('shows How it ranked above the grid with Builder view on, and one line in the dock', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36', '22']))
    await finish()
    await waitFor(() => expect(gridNames()).toHaveLength(2))
    expect(screen.queryByTestId('ranking-panel')).toBeNull()

    act(() => writeBuilderView(true))
    const panel = await screen.findByTestId('ranking-panel')
    const grid = screen.getByTestId('results-grid')
    expect(panel.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByTestId('results-view')).toContainElement(panel)
    expect(panel).toHaveTextContent('Kept 64 of 100')
    // The dock carries the one-line summary, never a second table.
    const dock = screen.getByTestId('chat-drawer')
    // The steps fold once the answer has settled; open them if they have.
    const fold = within(dock).queryByTestId('turn-fold')
    if (fold) fireEvent.click(fold)
    expect(await within(dock).findByTestId('ranking-summary')).toHaveTextContent('see the table above the results')
    expect(screen.getAllByTestId('ranking-panel')).toHaveLength(1)
  })

  it("leads with the answer's cards, a second search's among them, then the rest", async () => {
    CATALOG.set(96, card(96, 'Everyday Backpack'))
    CATALOG.set(95, card(95, 'Canvas Crossbody Bag'))
    CATALOG.set(97, card(97, 'Travel Bottles, Set of 4'))
    CATALOG.set(14, card(14, 'Linen Drawstring Trousers'))
    render(<Storefront />)
    await askFromTheHomeBar('For the trip')
    await emit(
      ROUTE_SHOPPING,
      SEARCH_RUNNING,
      { ...SEARCH_RUNNING, id: 'step-2' },
      searchDone(['96', '95', '14', '12']),
      searchDone(['97'], { id: 'step-2' }),
    )
    const answer =
      'Pack the Linen Drawstring Trousers at $40 for the heat, the Travel Bottles, Set of 4 at $40 ' +
      'for the bathroom bag, and the Everyday Backpack at $40 to carry it all.'
    await finish({
      ...COMPLETE,
      response: answer,
      products: [
        { id: 96, name: 'Everyday Backpack', price: 40 },
        { id: 14, name: 'Linen Drawstring Trousers', price: 40 },
        { id: 97, name: 'Travel Bottles, Set of 4', price: 40 },
      ],
    })
    const picks = ['Linen Drawstring Trousers', 'Travel Bottles, Set of 4', 'Everyday Backpack']
    // The answer's own order, then the first search's order without repeats.
    await waitFor(() => expect(gridNames()).toEqual([...picks, 'Canvas Crossbody Bag', 'Hadley Linen Shirt']))
    expect(pickNames()).toEqual(picks)
    expect(within(screen.getByTestId('results-grid')).getAllByText("Pellier's pick")).toHaveLength(3)
    expect(screen.getByTestId('results-count')).toHaveTextContent(/^5 pieces$/)
    // One bounded read for exactly the grid's ids: never a search of its own.
    expect(idReads.at(-1)).toBe('14,97,96,95,12')
    // The page and the answer read as one: the dock's cards are the grid's first.
    await waitFor(() => expect(dockCardNames()).toEqual(picks), { timeout: 4000 })
  })

  it('shows the first twelve pieces, then all of them on request', async () => {
    const ids = Array.from({ length: 14 }, (_, index) => String(200 + index))
    for (const id of ids) CATALOG.set(Number(id), card(Number(id), `Piece ${id}`))
    render(<Storefront />)
    await askFromTheHomeBar('Everything in linen')
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(ids))
    await finish()
    await waitFor(() => expect(gridNames()).toHaveLength(12))
    expect(gridNames()).toEqual(ids.slice(0, 12).map(id => `Piece ${id}`))
    expect(screen.getByTestId('results-count')).toHaveTextContent(/^14 pieces$/)
    const more = screen.getByTestId('results-show-all')
    expect(more).toHaveTextContent('Show all 14 pieces')

    fireEvent.click(more)
    expect(gridNames()).toEqual(ids.map(id => `Piece ${id}`))
    expect(screen.queryByTestId('results-show-all')).toBeNull()
    // The first piece it added takes the focus.
    expect(document.activeElement).toHaveTextContent('Piece 212')
  })

  it('has no Show all control when the result fits in twelve', async () => {
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36', '22', '31']))
    await finish()
    await waitFor(() => expect(gridNames()).toHaveLength(3))
    expect(screen.queryByTestId('results-show-all')).toBeNull()
    expect(screen.queryAllByText("Pellier's pick")).toHaveLength(0)
  })

  it('shows one table at a time when the turn ran two searches, never their numbers merged', async () => {
    const otherRanking = {
      ...RANKING,
      filters: { kept: 67, of: 100, removed: { budget: 33 } },
      rows: [{ ...RANKING.rows[0], product_id: '12', name: 'Hadley Linen Shirt' }],
    }
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(
      ROUTE_SHOPPING,
      SEARCH_RUNNING,
      { ...SEARCH_RUNNING, id: 'step-2' },
      searchDone(['36', '22']),
      searchDone(['12', '65'], { id: 'step-2', ranking: otherRanking }),
    )
    await finish({
      ...COMPLETE,
      response: 'The Ceramic Tumblers at $40, the Linen Napkins, Set of 4 at $40, and the Hadley Linen Shirt at $40.',
      products: [
        { id: 36, name: 'Ceramic Tumblers', price: 40 },
        { id: 22, name: 'Linen Napkins, Set of 4', price: 40 },
        { id: 12, name: 'Hadley Linen Shirt', price: 40 },
      ],
    })
    // The first search holds two of the three picks: the grid follows it.
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers', 'Linen Napkins, Set of 4', 'Hadley Linen Shirt']))

    act(() => writeBuilderView(true))
    const view = screen.getByTestId('results-view')
    const calls = await within(view).findAllByTestId('results-call')
    expect(calls.map(call => call.textContent)).toEqual(['12 found', '22 found'])
    expect(calls[0]).toHaveAttribute('aria-pressed', 'true')
    const panel = within(view).getByTestId('ranking-panel')
    expect(panel).toHaveTextContent('Kept 64 of 100')
    expect(panel).toHaveTextContent('Ceramic Tumblers')

    fireEvent.click(calls[1])
    expect(calls[1]).toHaveAttribute('aria-pressed', 'true')
    expect(within(view).getByTestId('ranking-panel')).toHaveTextContent('Kept 67 of 100')
    expect(within(view).getByTestId('ranking-panel')).toHaveTextContent('Hadley Linen Shirt')
    expect(within(view).getByTestId('ranking-panel')).not.toHaveTextContent('Kept 64 of 100')
    expect(within(view).getAllByTestId('ranking-panel')).toHaveLength(1)
  })

  it('returns to "This week at Pellier" from the wordmark, leaving the conversation', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    render(<Storefront />)
    await askFromTheHomeBar(ANNA_QUESTION)
    await emit(ROUTE_SHOPPING, SEARCH_RUNNING, searchDone(['36']))
    await finish()
    await waitFor(() => expect(gridNames()).toEqual(['Ceramic Tumblers']))
    expect(screen.getByTestId('pellier-hero-search')).toHaveValue(ANNA_QUESTION)
    const turnsBefore = stream.turns.length

    fireEvent.click(screen.getByTestId('pellier-wordmark'))
    expect(screen.queryByTestId('results-view')).toBeNull()
    expect(await screen.findByTestId('home-grid-title')).toHaveTextContent('This week at Pellier')
    expect(screen.getByTestId('home-grid')).toBeVisible()
    expect(screen.getByTestId('pellier-hero')).toHaveAttribute('data-compact', 'false')
    expect(screen.getByTestId('pellier-hero-search')).toHaveValue('')
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }))
    // The conversation is untouched.
    expect(within(screen.getByTestId('chat-drawer')).getByText(ANNA_QUESTION)).toBeInTheDocument()
    expect(stream.turns.length).toBe(turnsBefore)

    // On the store, words typed into the bar but not sent are cleared too.
    fireEvent.change(screen.getByTestId('pellier-hero-search'), { target: { value: 'linen' } })
    fireEvent.click(screen.getByTestId('pellier-wordmark'))
    expect(screen.getByTestId('pellier-hero-search')).toHaveValue('')
  })
})
