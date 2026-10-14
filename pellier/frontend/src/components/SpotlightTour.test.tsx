import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UIProvider } from '../contexts/UIContext'
import { TOUR } from '../copy'
import PellierSpotlight, { SPOTLIGHT_SEEN_KEY } from './PellierSpotlight'
import SurfaceNavigation from './SurfaceNavigation'

let reducedMotion = false
vi.mock('motion/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => reducedMotion,
}))

/** The shared header, plus the welcome where PellierPage mounts it. */
function renderAt(path: string, extra?: ReactNode) {
  return render(
    <UIProvider>
      <MemoryRouter initialEntries={[path]}>
        <SurfaceNavigation />
        {path === '/' ? <PellierSpotlight /> : null}
        {extra}
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
const welcome = () => screen.queryByRole('dialog', { name: 'Begin with the edit.' })
const titles = TOUR.STEPS.map(step => step.title)

function openFromHeader() {
  fireEvent.click(screen.getByRole('button', { name: TOUR.REPLAY }))
}

afterEach(() => {
  reducedMotion = false
  vi.restoreAllMocks()
})

describe('the tour after the welcome', () => {
  it('waits for the welcome, then opens at the Code Editor stop', () => {
    renderAt('/')
    expect(welcome()).toBeInTheDocument()
    expect(tour()).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Explore Pellier' }))

    expect(welcome()).toBeNull()
    const dialog = tour()
    expect(dialog).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
    expect(within(dialog!).getByText(`1 of ${titles.length}`)).toBeInTheDocument()
    expect(dialog).toHaveFocus()
  })

  it('opens when the welcome is skipped as well', () => {
    renderAt('/')
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[0]}`)
  })

  it('opens with neither once the welcome has been seen in this browser', () => {
    localStorage.setItem(SPOTLIGHT_SEEN_KEY, 'true')
    renderAt('/')
    expect(welcome()).toBeNull()
    expect(tour()).toBeNull()
  })

  it('opens with neither under ?tour=off', () => {
    window.history.pushState({}, '', '/?tour=off')
    try {
      renderAt('/')
      expect(welcome()).toBeNull()
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
    openFromHeader()
    expect(screen.getByTestId('spotlight-tour')).toHaveAttribute('data-target', 'none')
    expect(tour()).toHaveAttribute('data-placement', 'center')

    // jsdom lays nothing out, so give the Ask Pellier button a box.
    vi.spyOn(screen.getByTestId('header-ask-pellier'), 'getBoundingClientRect')
      .mockReturnValue(box(13, 900, 120, 38))
    fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    expect(screen.getByTestId('spotlight-tour-ring'))
      .toHaveStyle({ top: '7px', left: '894px', width: '132px', height: '50px' })
    expect(tour()).toHaveAttribute('data-placement', 'below')

    // No shopper chips on this page: that stop falls back.
    fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
    expect(tour()).toHaveAccessibleName(`Pellier tour: ${titles[2]}`)
    expect(screen.queryByTestId('spotlight-tour-ring')).toBeNull()
    expect(tour()).toHaveAttribute('data-placement', 'center')
  })

  it('rings whichever shopper chooser is laid out', () => {
    const hidden = document.createElement('div')
    hidden.dataset.tour = 'shoppers'
    const shown = document.createElement('div')
    shown.dataset.tour = 'shoppers'
    vi.spyOn(shown, 'getBoundingClientRect').mockReturnValue(box(130, 1016, 360, 40))
    renderAt('/product/17', null)
    document.body.append(hidden, shown)
    try {
      openFromHeader()
      fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
      fireEvent.click(screen.getByRole('button', { name: TOUR.NEXT }))
      expect(screen.getByTestId('spotlight-tour-ring'))
        .toHaveStyle({ top: '124px', left: '1010px', width: '372px', height: '52px' })
    } finally {
      hidden.remove()
      shown.remove()
    }
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
