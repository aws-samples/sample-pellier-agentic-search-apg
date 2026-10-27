import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UIProvider } from '../contexts/UIContext'
import { TOUR } from '../copy'
import { FIRST_VISIT_DELAY_MS, FirstVisitTour, SPOTLIGHT_SEEN_KEY } from './SpotlightTour'
import SurfaceNavigation from './SurfaceNavigation'

let reducedMotion = false
vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => reducedMotion,
}))

/** The shared header, plus the first-visit trigger where PellierPage mounts it. */
function renderAt(path: string) {
  return render(
    <UIProvider>
      <MemoryRouter initialEntries={[path]}>
        <SurfaceNavigation />
        {path === '/' ? <FirstVisitTour /> : null}
      </MemoryRouter>
    </UIProvider>,
  )
}

function box(top: number, left: number, width: number, height: number): DOMRect {
  return {
    top, left, width, height, right: left + width, bottom: top + height, x: left, y: top,
    toJSON: () => ({}),
  }
}

const tour = () => screen.queryByRole('dialog', { name: /^Pellier tour/ })
const titles = TOUR.STEPS.map(step => step.title)

function openFromHeader() {
  fireEvent.click(screen.getByRole('button', { name: TOUR.REPLAY }))
}

function waitForFirstVisit() {
  act(() => { vi.advanceTimersByTime(FIRST_VISIT_DELAY_MS) })
}

beforeEach(() => {
  localStorage.removeItem(SPOTLIGHT_SEEN_KEY)
  sessionStorage.removeItem(SPOTLIGHT_SEEN_KEY)
})

afterEach(() => {
  reducedMotion = false
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('the short tour', () => {
  it('has three stops', () => {
    expect(titles).toEqual(['Ask Pellier', 'Builder view', 'The Operator'])
  })

  it('opens on a first visit to the Storefront home, after the page lays out, and only once', () => {
    vi.useFakeTimers()
    const first = renderAt('/')
    expect(tour()).toBeNull()
    waitForFirstVisit()
    const dialog = tour()
    expect(dialog).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
    expect(within(dialog!).getByText(`1 of ${titles.length}`)).toBeInTheDocument()
    expect(dialog).toHaveFocus()
    expect(localStorage.getItem(SPOTLIGHT_SEEN_KEY)).toBe('true')

    first.unmount()
    renderAt('/')
    waitForFirstVisit()
    expect(tour()).toBeNull()
  })

  it('does not open by itself under ?tour=off', () => {
    vi.useFakeTimers()
    window.history.pushState({}, '', '/?tour=off')
    try {
      renderAt('/')
      waitForFirstVisit()
      expect(tour()).toBeNull()
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('never opens on the Operator, which offers no replay', () => {
    renderAt('/operator/reviews')
    expect(tour()).toBeNull()
    expect(screen.queryByTestId('tour-replay')).toBeNull()
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
    for (let i = 0; i < titles.length - 1; i += 1) {
      fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    }
    fireEvent.click(screen.getByRole('button', { name: TOUR.DONE }))
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
    // jsdom lays nothing out, so give the Ask Pellier button a box; Builder view has none.
    vi.spyOn(screen.getByTestId('header-ask-pellier'), 'getBoundingClientRect')
      .mockReturnValue(box(13, 900, 120, 38))
    openFromHeader()
    expect(screen.getByTestId('spotlight-tour-ring'))
      .toHaveStyle({ top: '7px', left: '894px', width: '132px', height: '50px' })
    expect(tour()).toHaveAttribute('data-placement', 'below')

    fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[1]}`)
    expect(screen.queryByTestId('spotlight-tour-ring')).toBeNull()
    expect(tour()).toHaveAttribute('data-placement', 'center')
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
