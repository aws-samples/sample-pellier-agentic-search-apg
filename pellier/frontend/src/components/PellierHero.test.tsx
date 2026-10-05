import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PellierHero from './PellierHero'
import { ASK_BAR } from '../copy'

const switchPersona = vi.fn()
const openDrawerWithQuery = vi.fn()
const openModal = vi.fn()

const PROFILES = [
  {
    id: 'fresh',
    display_name: 'Pellier guest',
    role_tag: 'New visitor',
    blurb: 'Live guest profile.',
    avatar_color: '#000',
    avatar_initial: 'P',
    hero_image: '/products/landing-hero-weekender.webp',
    hero_alt: 'Guest profile',
    hero_subheadline: 'Live guest profile.',
    stats: { visits: 0, orders: 0, last_seen_days: null },
  },
  {
    id: 'anna',
    display_name: 'Anna',
    role_tag: 'Gifting, ceremony, silk, glass',
    blurb: 'Live Anna profile.',
    avatar_color: '#000',
    avatar_initial: 'A',
    hero_image: '/products/hero-anna.png',
    hero_alt: 'Anna profile',
    hero_subheadline: 'Live Anna profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  },
  {
    id: 'marco',
    display_name: 'Marco',
    role_tag: 'Travel, utility, leather, linen',
    blurb: 'Live Marco profile.',
    avatar_color: '#000',
    avatar_initial: 'M',
    hero_image: '/products/hero-marco.png',
    hero_alt: 'Marco profile',
    hero_subheadline: 'Live Marco profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  },
  {
    id: 'theo',
    display_name: 'Theo',
    role_tag: 'Slow living, craft, stoneware, natural materials',
    blurb: 'Live Theo profile.',
    avatar_color: '#000',
    avatar_initial: 'T',
    hero_image: '/products/hero-theo.png',
    hero_alt: 'Theo profile',
    hero_subheadline: 'Live Theo profile.',
    stats: { visits: 1, orders: 1, last_seen_days: 1 },
  },
  {
    id: 'jessica',
    display_name: 'Jessica',
    role_tag: 'Home comforts, bath, soft light',
    blurb: 'Live Jessica profile.',
    avatar_color: '#000',
    avatar_initial: 'J',
    hero_image: '/products/house-ivory-cashmere-throw-1122.webp',
    hero_alt: 'Jessica profile',
    hero_subheadline: 'Live Jessica profile.',
    stats: { visits: 1, orders: 5, last_seen_days: 6 },
  },
  {
    id: 'nadia',
    display_name: 'Nadia',
    role_tag: 'Staff',
    blurb: 'Not a shopper.',
    avatar_color: '#000',
    avatar_initial: 'N',
    hero_image: '/assets/personas/nadia.png',
    hero_alt: 'Nadia',
    hero_subheadline: 'Not a shopper.',
    stats: { visits: 0, orders: 0, last_seen_days: null },
  },
]

let persona: (typeof PROFILES)[number] | null = null

vi.mock('../contexts/PersonaContext', () => ({
  usePersona: () => ({
    persona,
    switchPersona,
    switching: false,
    switchError: null,
  }),
}))

vi.mock('../contexts/UIContext', () => ({
  useUI: () => ({ openDrawerWithQuery, openModal }),
}))

function liveFetch(input: RequestInfo | URL): Promise<Response> {
  const url = String(input)
  if (url.startsWith('/api/personas')) {
    return Promise.resolve(new Response(JSON.stringify(PROFILES), { status: 200 }))
  }
  if (url.startsWith('/api/scenarios')) {
    return Promise.resolve(
      new Response(
        JSON.stringify({
          scenarios: [
            { id: 1, ordinal: 1, prompt: 'A live Aurora scenario' },
            { id: 2, ordinal: 2, prompt: 'A second live scenario' },
            { id: 3, ordinal: 3, prompt: 'A third live scenario' },
            { id: 4, ordinal: 4, prompt: 'The live build moment' },
            { id: 5, ordinal: 5, prompt: 'The optional capstone' },
          ],
        }),
        { status: 200 },
      ),
    )
  }
  return Promise.reject(new Error(`Unexpected request: ${url}`))
}

describe('PellierHero', () => {
  beforeEach(() => {
    persona = null
    switchPersona.mockReset()
    openDrawerWithQuery.mockReset()
    openModal.mockReset()
    vi.stubGlobal('fetch', vi.fn(liveFetch))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("leads with the store's statement, then the bar, and chooses no shopper here", () => {
    render(<PellierHero />)

    expect(screen.getByTestId('pellier-hero-eyebrow')).toHaveTextContent('Everyday prices, well made')
    expect(screen.getByTestId('pellier-hero-headline')).toHaveTextContent('Good things for every day.')
    expect(screen.getByTestId('pellier-hero-subheadline')).toHaveTextContent(
      'Linen, stoneware and the things that get used. Ask Pellier what you need and get a straight answer, from the real catalog.',
    )
    // Shoppers are chosen in the Ask Pellier panel, not on the home page.
    expect(screen.queryByTestId('persona-concierge')).not.toBeInTheDocument()
    expect(screen.queryByText('Choose who enters Pellier.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(Anna|Marco|Theo|Jessica)$/ })).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.map(([url]) => String(url))).not.toContain('/api/personas')
  })

  it("names the signed-in shopper's edit over their statement", () => {
    persona = PROFILES[1]
    render(<PellierHero />)

    expect(screen.getByTestId('pellier-hero-eyebrow')).toHaveTextContent("Anna's edit")
    expect(screen.getByTestId('pellier-hero-headline')).toHaveTextContent('Gifts, thoughtfully matched.')
  })

  it('folds to the bar while results show, keeping the statement for assistive tech', () => {
    render(<PellierHero compact query="A linen shirt" />)

    expect(screen.getByTestId('pellier-hero')).toHaveAttribute('data-compact', 'true')
    expect(screen.getByTestId('pellier-hero-search')).toHaveValue('A linen shirt')
    expect(screen.queryByTestId('pellier-hero-moments')).not.toBeInTheDocument()
  })

  it("submits the signed-in shopper's own prompt from Aurora", async () => {
    persona = PROFILES[1]
    render(<PellierHero />)

    fireEvent.click(await screen.findByRole('button', { name: 'A live Aurora scenario' }))
    expect(openDrawerWithQuery).toHaveBeenCalledWith('A live Aurora scenario')
    expect(vi.mocked(fetch).mock.calls.map(([url]) => String(url))).toContain('/api/scenarios?persona=anna')
  })

  it('shows one row of suggestions at a time, and swaps it as the shopper signs in and out', async () => {
    persona = null
    const view = render(<PellierHero />)
    expect(screen.getByTestId('pellier-hero-moments')).toBeInTheDocument()
    expect(screen.queryByTestId('pellier-hero-pills')).not.toBeInTheDocument()

    persona = PROFILES[1]
    view.rerender(<PellierHero />)
    const prompts = await screen.findByTestId('pellier-hero-pills')
    expect(within(prompts).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'A live Aurora scenario', 'A second live scenario', 'A third live scenario',
    ])
    expect(prompts).toHaveAccessibleName('Suggestions for Anna')
    expect(screen.queryByTestId('pellier-hero-moments')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'For the trip' })).not.toBeInTheDocument()

    persona = null
    view.rerender(<PellierHero />)
    expect(screen.getByTestId('pellier-hero-moments')).toBeInTheDocument()
    expect(screen.queryByTestId('pellier-hero-pills')).not.toBeInTheDocument()
  })

  it('shows no moments while a shopper\'s prompts are still loading', () => {
    persona = PROFILES[2]
    render(<PellierHero />)
    expect(screen.queryByTestId('pellier-hero-moments')).not.toBeInTheDocument()
  })

  it('shows only the three required workshop turns in the hero', async () => {
    persona = PROFILES[2]
    render(<PellierHero />)

    expect(
      await screen.findByRole('button', { name: 'A third live scenario' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'The live build moment' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'The optional capstone' }),
    ).not.toBeInTheDocument()
  })

  it('shows the search-or-ask bar with the store moments as chips, before a shopper is chosen', () => {
    persona = null
    render(<PellierHero />)

    const ask = screen.getByTestId('pellier-hero-search')
    expect(ask).toHaveAttribute('placeholder', 'Search or ask Pellier…')
    expect(ask).toHaveAccessibleName('Search or ask Pellier')
    const moments = screen.getByTestId('pellier-hero-moments')
    expect(within(moments).getAllByRole('button').map((b) => b.textContent)).toEqual([...ASK_BAR.MOMENTS])
    expect(screen.queryByTestId('persona-hero-image')).not.toBeInTheDocument()
  })

  it('sends a moment chip and a typed question to the docked panel', () => {
    persona = null
    const view = render(<PellierHero />)

    fireEvent.click(screen.getByRole('button', { name: 'For the trip' }))
    expect(openDrawerWithQuery).toHaveBeenCalledWith('For the trip')

    persona = PROFILES[1]
    view.rerender(<PellierHero />)
    fireEvent.change(screen.getByTestId('pellier-hero-search'), { target: { value: 'A linen shirt' } })
    fireEvent.click(screen.getByRole('button', { name: ASK_BAR.SEND }))
    expect(openDrawerWithQuery).toHaveBeenCalledWith('A linen shirt')
  })

  it('sends a question asked signed out straight to the docked panel', () => {
    persona = null
    render(<PellierHero />)

    fireEvent.change(screen.getByTestId('pellier-hero-search'), { target: { value: 'A gift under $100' } })
    fireEvent.submit(screen.getByRole('search'))
    expect(openDrawerWithQuery).toHaveBeenCalledWith('A gift under $100')
  })
})
