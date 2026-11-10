import { useEffect } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { Link, MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UIProvider, useUI } from '../contexts/UIContext'
import { TOUR } from '../copy'
import { FirstVisitTour } from './SpotlightTour'
import SurfaceNavigation from './SurfaceNavigation'
import {
  SPOTLIGHT_SEEN_KEY, TOUR_OPEN_DELAY_MS, chapterSeenKey, useTourChapter, type ChapterId,
} from './tourChapters'

let reducedMotion = false
vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => reducedMotion,
}))

const CHAPTERS = Object.keys(TOUR.CHAPTERS) as ChapterId[]
const titlesOf = (chapter: ChapterId): string[] => TOUR.CHAPTERS[chapter].map(stop => stop.title)
const titles = titlesOf('storefront')

/** Stands in for the component that owns a chapter's part of the page, such as a settled answer. */
function Chapter({ id, ready = true }: { id: ChapterId; ready?: boolean }) {
  useTourChapter(id, ready)
  return null
}

/** Stands in for the dock while a turn streams. */
function TurnRunning({ running }: { running: boolean }) {
  const { setTurnRunning } = useUI()
  useEffect(() => { setTurnRunning(running) }, [running, setTurnRunning])
  return null
}

/** The shared header, the first-visit trigger where PellierPage mounts it, and the page under test. */
function renderAt(path: string, page: React.ReactNode = null) {
  const tree = (content: React.ReactNode) => (
    <UIProvider>
      <MemoryRouter initialEntries={[path]}>
        <SurfaceNavigation />
        {path === '/' ? <FirstVisitTour /> : null}
        {content}
      </MemoryRouter>
    </UIProvider>
  )
  const view = render(tree(page))
  return { ...view, show: (next: React.ReactNode) => view.rerender(tree(next)) }
}

function box(top: number, left: number, width: number, height: number): DOMRect {
  return {
    top, left, width, height, right: left + width, bottom: top + height, x: left, y: top,
    toJSON: () => ({}),
  }
}

/** jsdom lays nothing out, so a control is on the page only once it is given a box. */
function layOut(element: Element, rect: DOMRect = box(300, 400, 240, 40)): Element {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue(rect)
  return element
}

/** The parts of the page each chapter rings, as the real components mark them. */
const ANSWER = (
  <>
    <p data-testid="turn-principal" />
    <button type="button" data-testid="turn-fold" />
    <section className="results-ranking" />
  </>
)
const DESK = (
  <>
    <nav className="op-bar-sections" />
    <div data-testid="operator-credit-request" />
    <button type="button" data-testid="operator-investigate" />
  </>
)
const PROPOSAL = (
  <>
    <div data-testid="operator-brief" />
    <ol data-testid="operator-credit-checks" />
    <div data-tour="credit-decision" />
  </>
)
const ANSWER_PARTS = ['[data-testid="turn-principal"]', '[data-testid="turn-fold"]', '.results-ranking']
const DESK_PARTS = ['.op-bar-sections', '[data-testid="operator-credit-request"]', '[data-testid="operator-investigate"]']
const PROPOSAL_PARTS = ['[data-testid="operator-brief"]', '[data-testid="operator-credit-checks"]', '[data-tour="credit-decision"]']

function layOutAll(selectors: string[]) {
  for (const selector of selectors) layOut(document.querySelector(selector)!)
}

const tour = () => screen.queryByRole('dialog', { name: /^Pellier tour/ })
const progress = () => tour()?.querySelector('.spotlight-tour-progress')?.textContent

function openFromHeader() {
  fireEvent.click(screen.getByRole('button', { name: TOUR.REPLAY }))
}

function waitForLayout() {
  act(() => { vi.advanceTimersByTime(TOUR_OPEN_DELAY_MS) })
}

/** Walks the open tour to its end, returning each stop's title. */
function walk(): string[] {
  const seen: string[] = []
  for (let guard = 0; guard < 20 && tour(); guard += 1) {
    seen.push(tour()!.getAttribute('aria-label')!.replace('Pellier tour: ', ''))
    const dialog = within(tour()!)
    fireEvent.click(dialog.queryByRole('button', { name: TOUR.NEXT }) ?? dialog.getByRole('button', { name: TOUR.DONE }))
  }
  return seen
}

beforeEach(() => {
  for (const chapter of CHAPTERS) localStorage.removeItem(chapterSeenKey(chapter))
  sessionStorage.removeItem(SPOTLIGHT_SEEN_KEY)
})

afterEach(() => {
  reducedMotion = false
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('the Storefront tour', () => {
  it('has four stops, and ends by asking for a shopper', () => {
    expect(titles).toEqual(['Ask Pellier', 'Builder view', 'The Operator', 'Choose a shopper'])
  })

  it('opens on a first visit to the Storefront home, after the page lays out, and only once', () => {
    vi.useFakeTimers()
    const first = renderAt('/')
    expect(tour()).toBeNull()
    waitForLayout()
    const dialog = tour()
    expect(dialog).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
    expect(within(dialog!).getByText(`1 of ${titles.length}`)).toBeInTheDocument()
    expect(dialog).toHaveFocus()
    expect(localStorage.getItem(SPOTLIGHT_SEEN_KEY)).toBe('true')

    first.unmount()
    renderAt('/')
    waitForLayout()
    expect(tour()).toBeNull()
  })

  it('does not open by itself under ?tour=off', () => {
    vi.useFakeTimers()
    window.history.pushState({}, '', '/?tour=off')
    try {
      renderAt('/')
      waitForLayout()
      expect(tour()).toBeNull()
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('shows Skip on every stop and walks forward and back', () => {
    renderAt('/product/17')
    openFromHeader()
    for (const [index, title] of titles.entries()) {
      const dialog = tour()!
      expect(dialog).toHaveAccessibleName(`Pellier tour: ${title}`)
      expect(within(dialog).getByRole('button', { name: TOUR.SKIP })).toBeVisible()
      expect(within(dialog).queryByRole('button', { name: TOUR.BACK }) === null).toBe(index === 0)
      if (index < titles.length - 1) {
        fireEvent.click(within(dialog).getByRole('button', { name: TOUR.NEXT }))
      }
    }
    fireEvent.click(within(tour()!).getByRole('button', { name: TOUR.BACK }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[titles.length - 2]}`)
  })

  it('closes on Done', () => {
    renderAt('/product/17')
    openFromHeader()
    expect(walk()).toEqual(titles)
    expect(tour()).toBeNull()
  })

  it('moves with the arrow keys and closes on Escape without passing it on', () => {
    const storeEscape = vi.fn()
    window.addEventListener('keydown', storeEscape)
    try {
      renderAt('/product/17')
      openFromHeader()
      fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' })
      expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[1]}`)
      fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' })
      expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
      fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
      expect(tour()).toBeNull()
      expect(storeEscape).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('keydown', storeEscape)
    }
  })

  it('replays from the header at the first stop and returns focus there', () => {
    renderAt('/product/17')
    const replay = screen.getByRole('button', { name: TOUR.REPLAY })
    replay.focus()
    fireEvent.click(replay)
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
    fireEvent.click(screen.getByRole('button', { name: TOUR.SKIP }))
    expect(tour()).toBeNull()
    expect(replay).toHaveFocus()
  })

  it('rings the control a stop names, and centres the card when it is missing', () => {
    renderAt('/product/17')
    // Give the Ask Pellier button a box; Builder view has none.
    layOut(screen.getByTestId('header-ask-pellier'), box(13, 900, 120, 38))
    openFromHeader()
    expect(screen.getByTestId('spotlight-tour-ring'))
      .toHaveStyle({ top: '7px', left: '894px', width: '132px', height: '50px' })
    expect(screen.getByTestId('spotlight-tour-ring')).toHaveAttribute('data-shape', 'control')
    expect(tour()).toHaveAttribute('data-placement', 'below')

    fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[1]}`)
    expect(screen.queryByTestId('spotlight-tour-ring')).toBeNull()
    expect(tour()).toHaveAttribute('data-placement', 'center')
  })

  it('sits over the lower edge of a panel too tall to sit beside', () => {
    renderAt('/product/17', ANSWER)
    layOutAll(ANSWER_PARTS.slice(0, 2))
    // jsdom's window is 768 tall; this panel leaves no room above or below it.
    layOut(document.querySelector('.results-ranking')!, box(10, 300, 400, 760))
    openFromHeader()
    for (let i = 0; i < titles.length + 2; i += 1) fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[2]}`)
    expect(tour()).toHaveAttribute('data-placement', 'over')
  })

  it.each([
    ['above the window', -500],
    ['below the window', 2000],
  ])('keeps the card on screen when its control has scrolled %s', (_where, top) => {
    renderAt('/product/17')
    layOut(screen.getByTestId('header-ask-pellier'), box(top, 900, 120, 38))
    openFromHeader()
    const cardTop = parseFloat(tour()!.style.top)
    expect(cardTop).toBeGreaterThanOrEqual(16)
    expect(cardTop).toBeLessThanOrEqual(window.innerHeight - 16)
  })

  it('keeps Tab inside the card', () => {
    renderAt('/product/17')
    openFromHeader()
    fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    const dialog = tour()!
    const last = within(dialog).getByRole('button', { name: TOUR.NEXT })
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(within(dialog).getByRole('button', { name: TOUR.SKIP })).toHaveFocus()
  })

  it('runs its motion only when reduced motion is not asked for', () => {
    renderAt('/product/17')
    openFromHeader()
    expect(screen.getByTestId('spotlight-tour')).toHaveAttribute('data-motion', 'full')
    fireEvent.click(screen.getByRole('button', { name: TOUR.SKIP }))
    reducedMotion = true
    openFromHeader()
    expect(screen.getByTestId('spotlight-tour')).toHaveAttribute('data-motion', 'reduce')
  })
})

describe('a chapter that opens when its part of the page is ready', () => {
  it.each([
    ['answer', '/product/17', ANSWER, ANSWER_PARTS],
    ['desk', '/operator/clients/CUST-JESSICA', DESK, DESK_PARTS],
    ['proposal', '/operator/clients/CUST-JESSICA', PROPOSAL, PROPOSAL_PARTS],
  ] as const)('%s: opens once, after the page lays out, and rings each of its controls', (chapter, path, page, parts) => {
    vi.useFakeTimers()
    const view = renderAt(path, <>{page}<Chapter id={chapter} /></>)
    layOutAll([...parts])
    expect(tour()).toBeNull()
    waitForLayout()
    expect(tour()).toHaveFocus()
    expect(screen.getByTestId('spotlight-tour')).toHaveAttribute('data-target', 'ring')
    expect(localStorage.getItem(chapterSeenKey(chapter))).toBe('true')
    expect(walk()).toEqual(titlesOf(chapter))

    view.unmount()
    renderAt(path, <>{page}<Chapter id={chapter} /></>)
    layOutAll([...parts])
    waitForLayout()
    expect(tour()).toBeNull()
  })

  it('waits until its component says the page is ready', () => {
    vi.useFakeTimers()
    const view = renderAt('/product/17', <>{ANSWER}<Chapter id="answer" ready={false} /></>)
    layOutAll(ANSWER_PARTS)
    waitForLayout()
    expect(tour()).toBeNull()

    view.show(<>{ANSWER}<Chapter id="answer" /></>)
    waitForLayout()
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[0]}`)
  })

  it('waits for a page that shows the whole chapter, so it is never used up half told', () => {
    vi.useFakeTimers()
    // A stock answer has no ranking panel.
    const view = renderAt('/product/17', <>{ANSWER}<Chapter id="answer" /></>)
    layOutAll(ANSWER_PARTS.slice(0, 2))
    waitForLayout()
    expect(tour()).toBeNull()
    expect(localStorage.getItem(chapterSeenKey('answer'))).toBeNull()

    // The next answer is a catalog one: its row asks again, and the ranking is on the page.
    view.show(<>{ANSWER}<Chapter id="answer" ready={false} /></>)
    layOutAll(ANSWER_PARTS)
    view.show(<>{ANSWER}<Chapter id="answer" /></>)
    waitForLayout()
    expect(progress()).toBe('1 of 3')
    expect(walk()).toEqual(titlesOf('answer'))
  })

  it('does not open over a question the visitor is writing', () => {
    vi.useFakeTimers()
    const page = (ready: boolean) => (
      <>{ANSWER}<textarea aria-label="Composer" defaultValue="" /><Chapter id="answer" ready={ready} /></>
    )
    const view = renderAt('/product/17', page(true))
    layOutAll(ANSWER_PARTS)
    const composer = screen.getByLabelText('Composer') as HTMLTextAreaElement
    composer.focus()
    fireEvent.change(composer, { target: { value: 'and in blue?' } })
    waitForLayout()
    expect(tour()).toBeNull()
    expect(composer).toHaveFocus()
    expect(localStorage.getItem(chapterSeenKey('answer'))).toBeNull()

    // Sent, the field is empty again; the next settled answer asks once more.
    fireEvent.change(composer, { target: { value: '' } })
    view.show(page(false))
    view.show(page(true))
    waitForLayout()
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[0]}`)
  })

  it('follows its control when the page moves under it without a scroll', () => {
    vi.useFakeTimers()
    renderAt('/operator/clients/CUST-JESSICA', <>{PROPOSAL}<Chapter id="proposal" /></>)
    layOutAll(PROPOSAL_PARTS)
    waitForLayout()
    expect(screen.getByTestId('spotlight-tour-ring')).toHaveStyle({ top: '294px' })

    // The record finishes loading above it and pushes the brief down.
    layOut(screen.getByTestId('operator-brief'), box(420, 400, 240, 40))
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByTestId('spotlight-tour-ring')).toHaveStyle({ top: '414px' })
  })

  it('stays closed, and unseen, with nothing on the page to ring', () => {
    vi.useFakeTimers()
    renderAt('/product/17', <>{ANSWER}<Chapter id="answer" /></>)
    waitForLayout()
    expect(tour()).toBeNull()
    expect(localStorage.getItem(chapterSeenKey('answer'))).toBeNull()
  })

  it('stays closed in a tab where tours are off', () => {
    vi.useFakeTimers()
    sessionStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
    renderAt('/operator/clients/CUST-JESSICA', <>{DESK}<Chapter id="desk" /></>)
    layOutAll(DESK_PARTS)
    waitForLayout()
    expect(tour()).toBeNull()
    expect(localStorage.getItem(chapterSeenKey('desk'))).toBeNull()
  })

  it('stays closed on the Operator under ?tour=off, and for the rest of the tab', () => {
    vi.useFakeTimers()
    window.history.pushState({}, '', '/operator?tour=off')
    try {
      renderAt('/operator/clients/CUST-JESSICA', <>{DESK}<Chapter id="desk" /></>)
      layOutAll(DESK_PARTS)
      waitForLayout()
      expect(tour()).toBeNull()
      expect(sessionStorage.getItem(SPOTLIGHT_SEEN_KEY)).toBe('true')
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('turns tours off for the tab from any page that opens with ?tour=off', () => {
    vi.useFakeTimers()
    // The clients list has no chapter of its own to check the address.
    window.history.pushState({}, '', '/operator?tour=off')
    const view = renderAt('/operator')
    window.history.pushState({}, '', '/operator/clients/CUST-JESSICA')
    try {
      expect(sessionStorage.getItem(SPOTLIGHT_SEEN_KEY)).toBe('true')
      view.show(<>{DESK}<Chapter id="desk" /></>)
      layOutAll(DESK_PARTS)
      waitForLayout()
      expect(tour()).toBeNull()
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('rings the latest answer when the dock holds several', () => {
    vi.useFakeTimers()
    renderAt('/product/17', <><p data-testid="turn-principal" />{ANSWER}<Chapter id="answer" /></>)
    layOutAll(ANSWER_PARTS.slice(1))
    const [earlier, latest] = screen.getAllByTestId('turn-principal')
    layOut(earlier, box(100, 1000, 300, 20))
    layOut(latest, box(500, 1000, 300, 20))
    waitForLayout()
    expect(screen.getByTestId('spotlight-tour-ring')).toHaveStyle({ top: '494px' })
  })

  it('brings a stop in the page into view, and leaves the header where it is', () => {
    vi.useFakeTimers()
    const scrolled: Element[] = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) { scrolled.push(this) }
    try {
      renderAt('/', <>{ANSWER}</>)
      layOutAll(ANSWER_PARTS)
      layOut(screen.getByTestId('header-ask-pellier'), box(13, 900, 120, 38))
      waitForLayout()
      expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
      expect(scrolled).toEqual([])
      fireEvent.click(screen.getByRole('button', { name: TOUR.SKIP }))

      openFromHeader()
      for (let i = 0; i < titles.length; i += 1) fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
      expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[0]}`)
      expect(scrolled).toContain(screen.getByTestId('turn-principal'))
      expect(scrolled).not.toContain(screen.getByTestId('header-ask-pellier'))
    } finally {
      Element.prototype.scrollIntoView = original
    }
  })

  it('gives a panel a card-shaped ring', () => {
    vi.useFakeTimers()
    renderAt('/operator/clients/CUST-JESSICA', <>{PROPOSAL}<Chapter id="proposal" /></>)
    layOutAll(PROPOSAL_PARTS)
    waitForLayout()
    expect(screen.getByTestId('spotlight-tour-ring')).toHaveAttribute('data-shape', 'panel')
  })

  it('follows the orientation instead of opening over it', () => {
    vi.useFakeTimers()
    // A returning shopper's first visit: the page already holds an answer.
    renderAt('/', <>{ANSWER}<Chapter id="answer" /></>)
    layOutAll(ANSWER_PARTS)
    waitForLayout()
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
    expect(progress()).toBe(`1 of ${titles.length}`)
    expect(localStorage.getItem(chapterSeenKey('answer'))).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: TOUR.SKIP }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[0]}`)
    expect(progress()).toBe(`1 of ${titlesOf('answer').length}`)
    expect(localStorage.getItem(chapterSeenKey('answer'))).toBe('true')
  })

  it('waits for a running turn to finish', () => {
    vi.useFakeTimers()
    const view = renderAt('/product/17', <>{ANSWER}<Chapter id="answer" /><TurnRunning running /></>)
    layOutAll(ANSWER_PARTS)
    waitForLayout()
    expect(tour()).toBeNull()

    view.show(<>{ANSWER}<Chapter id="answer" /><TurnRunning running={false} /></>)
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('answer')[0]}`)
  })

  it('opens once in a page even when the browser keeps no record of it', () => {
    vi.useFakeTimers()
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new Error('storage is full') })
    const view = renderAt('/product/17', <>{ANSWER}<Chapter id="answer" /></>)
    layOutAll(ANSWER_PARTS)
    waitForLayout()
    fireEvent.click(screen.getByRole('button', { name: TOUR.SKIP }))

    // The next answer settles: its row asks again.
    view.show(<>{ANSWER}<Chapter id="answer" ready={false} /></>)
    view.show(<>{ANSWER}<Chapter id="answer" /></>)
    waitForLayout()
    expect(tour()).toBeNull()
  })

  it('closes when the visitor moves to another page', () => {
    vi.useFakeTimers()
    renderAt('/product/17', <>{ANSWER}<Chapter id="answer" /><Link to="/about">About</Link></>)
    layOutAll(ANSWER_PARTS)
    waitForLayout()
    expect(tour()).not.toBeNull()
    fireEvent.click(screen.getByRole('link', { name: 'About' }))
    expect(tour()).toBeNull()
  })
})

describe('the replay button', () => {
  it('is on the Operator too, where nothing opens by itself', () => {
    vi.useFakeTimers()
    renderAt('/operator/reviews')
    waitForLayout()
    expect(tour()).toBeNull()
    expect(screen.getByTestId('tour-replay')).toBeInTheDocument()
  })

  it('is not on the sign-in page', () => {
    renderAt('/signin')
    expect(screen.queryByTestId('tour-replay')).toBeNull()
  })

  it('plays the Operator chapters that are on the page, without the Storefront stops', () => {
    renderAt('/operator/clients/CUST-JESSICA', <>{DESK}{PROPOSAL}</>)
    layOutAll([...DESK_PARTS, ...PROPOSAL_PARTS])
    openFromHeader()
    expect(walk()).toEqual([...titlesOf('desk'), ...titlesOf('proposal')])
  })

  it('plays what a signed-out desk has: the two sections', () => {
    renderAt('/operator', <nav className="op-bar-sections" />)
    layOutAll(['.op-bar-sections'])
    openFromHeader()
    expect(progress()).toBe('1 of 1')
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titlesOf('desk')[0]}`)
  })

  it('opens nothing when the Operator has nothing on the page to ring', () => {
    renderAt('/operator')
    openFromHeader()
    expect(tour()).toBeNull()
  })

  it('leaves out a stop whose control is not on the page', () => {
    // A stock answer has no ranking panel.
    renderAt('/product/17', ANSWER)
    layOutAll(ANSWER_PARTS.slice(0, 2))
    openFromHeader()
    expect(walk()).toEqual([...titles, ...titlesOf('answer').slice(0, 2)])
  })

  it('does not ring a ranking panel that says it has no ranking to show', () => {
    renderAt('/product/17', (
      <>
        <p data-testid="turn-principal" />
        <button type="button" data-testid="turn-fold" />
        <div className="results-ranking tn-rank-unavailable" />
      </>
    ))
    layOutAll(ANSWER_PARTS)
    openFromHeader()
    expect(walk()).toEqual([...titles, ...titlesOf('answer').slice(0, 2)])
  })

  it('follows the orientation with the answer chapter when an answer is on the page', () => {
    renderAt('/product/17', ANSWER)
    layOutAll(ANSWER_PARTS)
    openFromHeader()
    expect(walk()).toEqual([...titles, ...titlesOf('answer')])
  })

  it('replays a chapter the visitor has already seen', () => {
    localStorage.setItem(chapterSeenKey('answer'), 'true')
    renderAt('/product/17', ANSWER)
    layOutAll(ANSWER_PARTS)
    openFromHeader()
    expect(walk()).toEqual([...titles, ...titlesOf('answer')])
  })
})
