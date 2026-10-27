import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ANNOUNCEMENTS, ANNOUNCEMENT_CONTROLS } from '../copy'
import AnnouncementBar from './AnnouncementBar'

const motion = vi.hoisted(() => ({ reduce: false }))
vi.mock('motion/react', async importOriginal => ({
  ...(await importOriginal<typeof import('motion/react')>()),
  useReducedMotion: () => motion.reduce,
}))

function shownNote(): string {
  const active = screen.getByTestId('announcement-bar').querySelector('[data-active="true"]')
  return active?.textContent ?? ''
}

const note = (i: number) => `${ANNOUNCEMENTS[i].VERB}${ANNOUNCEMENTS[i].TEXT}`

beforeEach(() => {
  motion.reduce = false
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AnnouncementBar', () => {
  it('starts on the service note and moves to the next every five seconds, then wraps', () => {
    render(<AnnouncementBar />)
    expect(shownNote()).toBe(note(0))
    act(() => { vi.advanceTimersByTime(4_999) })
    expect(shownNote()).toBe(note(0))
    act(() => { vi.advanceTimersByTime(1) })
    expect(shownNote()).toBe(note(1))
    act(() => { vi.advanceTimersByTime(5_000 * (ANNOUNCEMENTS.length - 1)) })
    expect(shownNote()).toBe(note(0))
  })

  it('exposes only the shown note to assistive technology and never announces a change', () => {
    render(<AnnouncementBar />)
    const bar = screen.getByRole('region', { name: 'Storefront announcements' })
    expect(bar).not.toHaveAttribute('aria-live')
    const hidden = bar.querySelectorAll('.pellier-announcement-note[aria-hidden="true"]')
    expect(hidden).toHaveLength(ANNOUNCEMENTS.length - 1)
  })

  it('stops on the pause button and starts again on play', () => {
    render(<AnnouncementBar />)
    fireEvent.click(screen.getByRole('button', { name: ANNOUNCEMENT_CONTROLS.PAUSE }))
    act(() => { vi.advanceTimersByTime(12_000) })
    expect(shownNote()).toBe(note(0))
    fireEvent.click(screen.getByRole('button', { name: ANNOUNCEMENT_CONTROLS.PLAY }))
    act(() => { vi.advanceTimersByTime(5_000) })
    expect(shownNote()).toBe(note(1))
  })

  it('holds while a pointer rests on the bar', () => {
    render(<AnnouncementBar />)
    const bar = screen.getByTestId('announcement-bar')
    fireEvent.pointerEnter(bar)
    act(() => { vi.advanceTimersByTime(12_000) })
    expect(shownNote()).toBe(note(0))
    fireEvent.pointerLeave(bar)
    act(() => { vi.advanceTimersByTime(5_000) })
    expect(shownNote()).toBe(note(1))
  })

  it('keeps the service note still, with no pause button, under reduced motion', () => {
    motion.reduce = true
    render(<AnnouncementBar />)
    act(() => { vi.advanceTimersByTime(12_000) })
    expect(shownNote()).toBe(note(0))
    expect(screen.queryByTestId('announcement-pause')).toBeNull()
    expect(screen.getByTestId('announcement-bar')).toHaveAttribute('data-rotates', 'false')
  })
})
